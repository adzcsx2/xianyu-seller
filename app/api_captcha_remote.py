"""
刮刮乐远程控制 API 路由
提供 WebSocket 和 HTTP 接口用于远程操作滑块验证
"""

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
import asyncio
import time
from loguru import logger

from utils.captcha_remote_control import captcha_controller

# 创建路由器
router = APIRouter(prefix="/api/captcha", tags=["captcha"])
security = HTTPBearer(auto_error=False)
_token_resolver: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None


def configure_captcha_auth(
    token_resolver: Callable[[str], Optional[Dict[str, Any]]]
) -> None:
    """由主应用注入会话解析器，避免验证码路由复制认证规则。"""
    global _token_resolver
    _token_resolver = token_resolver


def require_captcha_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
    if not credentials or _token_resolver is None:
        raise HTTPException(status_code=401, detail="未授权访问")
    user = _token_resolver(credentials.credentials)
    if not user:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return user


def require_owned_session(session_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    session_data = captcha_controller.active_sessions.get(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session_data.get("owner_user_id") != user.get("user_id"):
        raise HTTPException(status_code=403, detail="无权访问该验证会话")
    return session_data


async def authenticate_websocket(websocket: WebSocket) -> Optional[Dict[str, Any]]:
    """要求 WebSocket 首帧携带 token，避免把凭据放入 URL/代理日志。"""
    try:
        payload = await asyncio.wait_for(websocket.receive_json(), timeout=10)
    except Exception:
        await websocket.send_json({"type": "error", "message": "认证超时或认证消息无效"})
        await websocket.close(code=4401)
        return None

    token = payload.get("token") if payload.get("type") == "authenticate" else None
    user = _token_resolver(token) if token and _token_resolver is not None else None
    if not user:
        await websocket.send_json({"type": "error", "message": "认证失败，请重新登录"})
        await websocket.close(code=4401)
        return None
    return user


class MouseEvent(BaseModel):
    """鼠标事件模型"""
    session_id: str
    event_type: str  # down, move, up
    x: int
    y: int


class SessionCheckRequest(BaseModel):
    """会话检查请求"""
    session_id: str


# =============================================================================
# WebSocket 端点 - 实时通信
# =============================================================================

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket 连接用于实时传输截图和接收鼠标事件
    """
    await websocket.accept()
    current_user = await authenticate_websocket(websocket)
    if current_user is None:
        return
    logger.info(f"🔌 WebSocket 认证成功: {session_id}")

    try:
        # 发送初始会话信息
        # 后端 start_manual_captcha → open_manual_session 要先抢 browser_limit 槽位
        # 才能打开浏览器截图建会话，前端 WebSocket 可能比会话创建先到。原实现在
        # 会话不存在时立即发 error + close，前端静默重连但看不到任何反馈，
        # 弹窗一直停在「正在服务器上打开验证页面」。这里改为轮询等待最多 30 秒，
        # 给后端足够时间完成浏览器启动和截图。
        if session_id not in captcha_controller.active_sessions:
            wait_deadline = time.monotonic() + 30
            while time.monotonic() < wait_deadline:
                await asyncio.sleep(1)
                if session_id in captcha_controller.active_sessions:
                    break
            else:
                await websocket.send_json({
                    'type': 'error',
                    'message': '会话创建超时，可能是服务器繁忙或浏览器启动失败，请稍后重试'
                })
                await websocket.close()
                return

        if session_id in captcha_controller.active_sessions:
            session_data = captcha_controller.active_sessions[session_id]
            if session_data.get("owner_user_id") != current_user.get("user_id"):
                await websocket.send_json({
                    'type': 'error',
                    'message': '无权访问该验证会话',
                })
                await websocket.close(code=4403)
                return

            # 只有完成认证和归属校验后才注册连接、发送截图。
            captcha_controller.websocket_connections[session_id] = websocket
            await websocket.send_json({
                'type': 'session_info',
                'screenshot': session_data['screenshot'],
                'captcha_info': session_data['captcha_info'],
                'viewport': session_data['viewport']
            })
            
            # 不启动自动刷新，改为只在操作时更新（极速优化）
            # refresh_task = asyncio.create_task(
            #     captcha_controller.auto_refresh_screenshot(session_id, interval=1.5)
            # )
        else:
            await websocket.send_json({
                'type': 'error',
                'message': '会话不存在'
            })
            await websocket.close()
            return
        
        # 持续接收客户端消息
        while True:
            data = await websocket.receive_json()
            msg_type = data.get('type')
            
            if msg_type == 'mouse_event':
                # 处理鼠标事件
                event_type = data.get('event_type')
                x = data.get('x')
                y = data.get('y')
                
                success = await captcha_controller.handle_mouse_event(
                    session_id, event_type, x, y
                )
                
                if success:
                    # 只在鼠标释放后才检查完成状态
                    if event_type == 'up':
                        # 等待页面更新（给验证码一些反应时间）
                        await asyncio.sleep(1.0)
                        
                        # 多次确认滑块确实消失
                        completed = await captcha_controller.check_completion(session_id)
                        
                        if completed:
                            # 再次确认（避免误判）
                            await asyncio.sleep(0.5)
                            completed = await captcha_controller.check_completion(session_id)
                        
                        if completed:
                            await websocket.send_json({
                                'type': 'completed',
                                'message': '验证成功！'
                            })
                            logger.success(f"✅ 验证完成: {session_id}")
                            break
                        else:
                            # 更新截图显示验证结果
                            screenshot = await captcha_controller.update_screenshot(session_id)
                            if screenshot:
                                await websocket.send_json({
                                    'type': 'screenshot_update',
                                    'screenshot': screenshot
                                })
                    else:
                        # 按下或移动时，实时更新截图（截取整个验证码容器）
                        if event_type in ['down', 'move']:
                            # 截取整个验证码容器，降低质量换取速度
                            screenshot = await captcha_controller.update_screenshot(session_id, quality=30)
                            if screenshot:
                                await websocket.send_json({
                                    'type': 'screenshot_update',
                                    'screenshot': screenshot
                                })
            
            elif msg_type == 'check_completion':
                # 手动检查完成状态
                completed = await captcha_controller.check_completion(session_id)
                await websocket.send_json({
                    'type': 'completion_status',
                    'completed': completed
                })
                
                if completed:
                    break
            
            elif msg_type == 'ping':
                # 心跳
                await websocket.send_json({'type': 'pong'})
    
    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket 连接断开: {session_id}")
    
    except Exception as e:
        logger.error(f"❌ WebSocket 错误: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    finally:
        # 清理
        if captcha_controller.websocket_connections.get(session_id) is websocket:
            del captcha_controller.websocket_connections[session_id]
        
        logger.info(f"🔒 WebSocket 会话结束: {session_id}")


# =============================================================================
# HTTP 端点 - REST API
# =============================================================================

@router.get("/sessions")
async def get_active_sessions(
    current_user: Dict[str, Any] = Depends(require_captcha_user),
):
    """获取所有活跃的验证会话"""
    sessions = []
    for session_id, data in captcha_controller.active_sessions.items():
        if data.get("owner_user_id") != current_user.get("user_id"):
            continue
        sessions.append({
            'session_id': session_id,
            'completed': data.get('completed', False),
            'has_websocket': session_id in captcha_controller.websocket_connections
        })
    
    return {
        'count': len(sessions),
        'sessions': sessions
    }


@router.get("/session/{session_id}")
async def get_session_info(
    session_id: str,
    current_user: Dict[str, Any] = Depends(require_captcha_user),
):
    """获取指定会话的信息"""
    session_data = require_owned_session(session_id, current_user)
    
    return {
        'session_id': session_id,
        'screenshot': session_data['screenshot'],
        'captcha_info': session_data['captcha_info'],
        'viewport': session_data['viewport'],
        'completed': session_data.get('completed', False)
    }


@router.get("/screenshot/{session_id}")
async def get_screenshot(
    session_id: str,
    current_user: Dict[str, Any] = Depends(require_captcha_user),
):
    """获取最新截图"""
    require_owned_session(session_id, current_user)
    screenshot = await captcha_controller.update_screenshot(session_id)
    
    if not screenshot:
        raise HTTPException(status_code=404, detail="无法获取截图")
    
    return {'screenshot': screenshot}


@router.post("/mouse_event")
async def handle_mouse_event(
    event: MouseEvent,
    current_user: Dict[str, Any] = Depends(require_captcha_user),
):
    """处理鼠标事件（HTTP方式，不推荐，建议使用WebSocket）"""
    require_owned_session(event.session_id, current_user)
    success = await captcha_controller.handle_mouse_event(
        event.session_id,
        event.event_type,
        event.x,
        event.y
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="处理失败")
    
    # 检查是否完成
    completed = await captcha_controller.check_completion(event.session_id)
    
    return {
        'success': True,
        'completed': completed
    }


@router.post("/check_completion")
async def check_completion(
    request: SessionCheckRequest,
    current_user: Dict[str, Any] = Depends(require_captcha_user),
):
    """检查验证是否完成"""
    require_owned_session(request.session_id, current_user)
    completed = await captcha_controller.check_completion(request.session_id)
    
    return {
        'session_id': request.session_id,
        'completed': completed
    }


@router.delete("/session/{session_id}")
async def close_session(
    session_id: str,
    current_user: Dict[str, Any] = Depends(require_captcha_user),
):
    """关闭会话"""
    require_owned_session(session_id, current_user)
    await captcha_controller.close_session(session_id)
    return {'success': True}


# =============================================================================
# 前端页面
# =============================================================================

@router.get("/status/{session_id}")
async def get_captcha_status(
    session_id: str,
    current_user: Dict[str, Any] = Depends(require_captcha_user),
):
    """
    获取验证状态
    用于前端轮询检查验证是否完成
    """
    require_owned_session(session_id, current_user)
    try:
        is_completed = captcha_controller.is_completed(session_id)
        session_exists = captcha_controller.session_exists(session_id)
        
        return {
            "success": True,
            "completed": is_completed,
            "session_exists": session_exists,
            "session_id": session_id
        }
    except Exception as e:
        logger.error(f"获取验证状态失败: {e}")
        return {
            "success": False,
            "completed": False,
            "session_exists": False,
            "session_id": session_id,
            "error": str(e)
        }

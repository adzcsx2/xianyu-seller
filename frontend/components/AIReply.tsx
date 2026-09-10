import React, { useEffect, useMemo, useState } from 'react';
import {
  Bot,
  CheckCircle2,
  Eye,
  EyeOff,
  Loader2,
  MessageSquareText,
  Play,
  RefreshCw,
  Save,
  ShieldCheck,
} from 'lucide-react';
import { AccountDetail, AIReplySettings, AIReplyStyle, Item } from '../types';
import {
  getAccountAISettings,
  getAccountDetails,
  getAvailableAIModels,
  getItems,
  getAIReplyStyle,
  testAIConnection,
  updateAccountAISettings,
  updateAIReplyStyle,
} from '../services/api';
import { notify } from '../services/feedback';
import { useFeatureFlags } from '../contexts/FeatureFlagsContext';
import { EmptyState, PageHeader, PageLoading, SectionHeader } from './ui';

const defaultSettings: AIReplySettings = {
  ai_enabled: false,
  model_name: '',
  api_key: '',
  api_key_configured: false,
  base_url: '',
  user_agent: 'codex_cli_rs/0.0.0 (Hermes Agent)',
  context_enabled: true,
  context_message_limit: 12,
  context_expire_minutes: 120,
};

const defaultReplyStyle = '语气自然、友好，略带俏皮，像真实的闲鱼卖家。优先用一到两句短句直接回答，可少量使用语气词；不要复述规则，不主动扩展买家没有询问的内容，避免客服腔、夸张承诺和连续表情。';

const AIReply: React.FC = () => {
  const { isEnabled } = useFeatureFlags();
  const aiReplyEnabled = isEnabled('feature_ai_reply_enabled');
  const [accounts, setAccounts] = useState<AccountDetail[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [selectedItemId, setSelectedItemId] = useState('');
  const [settings, setSettings] = useState<AIReplySettings>(defaultSettings);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState('');
  const [testMessage, setTestMessage] = useState('你好，这个商品现在还能买吗？');
  const [testReply, setTestReply] = useState('');
  const [replyStyle, setReplyStyle] = useState(defaultReplyStyle);
  const [replyStyleVersion, setReplyStyleVersion] = useState(1);
  const [styleSaving, setStyleSaving] = useState(false);

  const selectedAccount = useMemo(
    () => accounts.find(account => account.id === selectedAccountId),
    [accounts, selectedAccountId],
  );
  const availableItems = useMemo(
    () => items.filter(item => item.cookie_id === selectedAccountId),
    [items, selectedAccountId],
  );

  useEffect(() => {
    Promise.all([getAccountDetails(), getItems()])
      .then(([data, itemData]) => {
        setAccounts(data);
        setItems(itemData);
        setSelectedAccountId(data[0]?.id || '');
        setSelectedItemId(itemData.find(item => item.cookie_id === data[0]?.id)?.item_id || '');
      })
      .catch(error => notify(error instanceof Error ? error.message : '账号加载失败', 'error'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    getAIReplyStyle()
      .then((data: AIReplyStyle) => {
        setReplyStyle(data.reply_style || defaultReplyStyle);
        setReplyStyleVersion(data.version);
      })
      .catch(error => notify(error instanceof Error ? error.message : '回复风格加载失败', 'error'));
  }, []);

  useEffect(() => {
    setSelectedItemId(availableItems[0]?.item_id || '');
  }, [selectedAccountId, availableItems]);

  useEffect(() => {
    if (!selectedAccountId) return;
    setLoading(true);
    setTestReply('');
    setShowApiKey(false);
    getAccountAISettings(selectedAccountId)
      .then(data => {
        setSettings({ ...defaultSettings, ...data });
        if (data.ai_env_overrides?.api_key) setShowApiKey(true);
      })
      .catch(error => notify(error instanceof Error ? error.message : 'AI配置加载失败', 'error'))
      .finally(() => setLoading(false));
  }, [selectedAccountId]);

  const updateSetting = <K extends keyof AIReplySettings>(key: K, value: AIReplySettings[K]) => {
    setSettings(current => ({ ...current, [key]: value }));
  };

  const loadAvailableModels = async (cookieId = selectedAccountId) => {
    if (!cookieId) return;
    setModelsLoading(true);
    setModelsError('');
    try {
      const result = await getAvailableAIModels(cookieId);
      setAvailableModels(result.models || []);
      if (!result.models?.length) setModelsError('模型服务没有返回可用模型');
    } catch (error) {
      setModelsError(`获取模型列表失败：${(error as Error).message}`);
    } finally {
      setModelsLoading(false);
    }
  };

  useEffect(() => {
    setAvailableModels([]);
    setModelsError('');
    void loadAvailableModels();
  }, [selectedAccountId]);

  const handleSave = async () => {
    if (!aiReplyEnabled) return;
    if (!selectedAccountId) {
      notify('请先选择账号', 'warning');
      return;
    }
    if (!settings.model_name.trim() || !settings.base_url.trim()) {
      notify('模型名称和接口地址不能为空', 'warning');
      return;
    }

    setSaving(true);
    try {
      await updateAccountAISettings(selectedAccountId, settings);
      const refreshed = await getAccountAISettings(selectedAccountId);
      setSettings({ ...defaultSettings, ...refreshed });
      if (refreshed.ai_env_overrides?.api_key) setShowApiKey(true);
      notify('人工智能回复配置已保存', 'success');
    } catch (error) {
      notify(error instanceof Error ? error.message : 'AI配置保存失败', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!aiReplyEnabled) return;
    if (!selectedAccountId || !selectedItemId || !testMessage.trim()) {
      notify('请选择账号、真实商品并输入测试消息', 'warning');
      return;
    }
    setTesting(true);
    setTestReply('');
    try {
      const result = await testAIConnection(selectedAccountId, {
        message: testMessage.trim(),
        item_id: selectedItemId,
      });
      setTestReply(result.reply || result.message || '测试完成');
      notify('AI回复测试完成', 'success');
    } catch (error) {
      notify(error instanceof Error ? error.message : 'AI回复测试失败', 'error');
    } finally {
      setTesting(false);
    }
  };

  const handleSaveStyle = async () => {
    if (!aiReplyEnabled) return;
    if (!replyStyle.trim()) {
      notify('回复风格不能为空', 'warning');
      return;
    }
    setStyleSaving(true);
    try {
      const data = await updateAIReplyStyle(replyStyleVersion, replyStyle.trim());
      setReplyStyle(data.reply_style);
      setReplyStyleVersion(data.version);
      notify('全局回复风格已保存', 'success');
    } catch (error: any) {
      notify(error?.response?.status === 409 ? '回复风格版本已变化，请重新加载' : (error instanceof Error ? error.message : '回复风格保存失败'), 'error');
    } finally {
      setStyleSaving(false);
    }
  };

  if (loading && accounts.length === 0) {
    return <PageLoading label="正在加载 AI 回复配置" />;
  }

  return (
    <div className="page-stack animate-fade-in">
      <PageHeader
        title="AI 回复"
        description="按账号配置模型连接和上下文记忆；商品业务规则请在知识库中维护。"
        icon={Bot}
        actions={(
          <div className="flex min-w-0 flex-wrap items-end gap-2">
            <label className="min-w-0 sm:w-72">
              <span className="field-label">当前账号</span>
              <select
                value={selectedAccountId}
                onChange={event => setSelectedAccountId(event.target.value)}
                className="ios-input w-full rounded-md px-3 py-2 text-sm font-semibold"
              >
                {accounts.map(account => (
                  <option key={account.id} value={account.id}>
                    {account.nickname || account.remark || `账号 ${account.id.slice(0, 8)}`}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || !selectedAccountId || !aiReplyEnabled}
              className="ios-btn-primary flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {saving ? '保存中' : '保存配置'}
            </button>
          </div>
        )}
      />

      {!selectedAccountId ? (
        <EmptyState
          icon={Bot}
          title="暂无可配置账号"
          description="请先在账号管理中添加并登录闲鱼账号。"
        />
      ) : (
        <>
          <section className="section-panel grid gap-4 p-4 lg:grid-cols-[1fr_auto] lg:items-center">
            <div>
              <div className="flex items-center gap-2 font-bold text-gray-900">
                <MessageSquareText className="h-5 w-5" />
                {selectedAccount?.nickname || selectedAccount?.remark || selectedAccountId}
              </div>
              <p className="mt-1 text-sm text-gray-500">
                回复优先级：关键词回复 → 人工智能回复 → 默认回复。AI失败时不会中断消息处理。
              </p>
            </div>
            <label className="flex cursor-pointer items-center gap-3">
              <span className="text-sm font-bold text-gray-700">
                {settings.ai_enabled ? '已启用' : '已停用'}
              </span>
              <input
                type="checkbox"
                checked={settings.ai_enabled}
                onChange={event => updateSetting('ai_enabled', event.target.checked)}
                className="h-5 w-5 accent-yellow-400"
              />
            </label>
          </section>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(340px,0.65fr)]">
            <div className="space-y-6">
              <section className="section-panel">
                <SectionHeader
                  title="模型连接"
                  description="支持 OpenAI 兼容接口；密钥留空时保留服务器中已有配置。"
                  icon={Bot}
                />
                <div className="grid gap-4 p-5 md:grid-cols-2">
                  <div className="md:col-span-2 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-gray-800">
                        请显式配置你自己的 AI 服务
                      </p>
                      <p className="mt-0.5 text-xs text-gray-600">
                        系统不会内置或自动连接第三方服务；请填写兼容 OpenAI 协议的接口地址和密钥。
                      </p>
                    </div>
                  </div>
                  <label>
                    <span className="mb-1.5 flex items-center gap-2 text-sm font-semibold text-gray-700">
                      接口地址
                      {settings.ai_env_overrides?.base_url && (
                        <span className="text-xs font-normal text-blue-600">已从 .env 加载</span>
                      )}
                    </span>
                    <input
                      value={settings.base_url}
                      onChange={event => updateSetting('base_url', event.target.value)}
                      className="ios-input w-full rounded-md px-3 py-2.5 text-sm"
                      placeholder="未配置，例如 https://api.openai.com/v1"
                    />
                  </label>
                  <label>
                    <span className="mb-1.5 flex items-center justify-between gap-2 text-sm font-semibold text-gray-700">
                      <span className="flex items-center gap-2">
                        模型名称
                        {settings.ai_env_overrides?.model_name && (
                          <span className="text-xs font-normal text-blue-600">已从 .env 加载</span>
                        )}
                      </span>
                      <button
                        type="button"
                        onClick={() => void loadAvailableModels()}
                        disabled={modelsLoading}
                        className="inline-flex items-center gap-1 text-xs font-normal text-blue-600 hover:underline disabled:opacity-50"
                      >
                        <RefreshCw className={`h-3.5 w-3.5 ${modelsLoading ? 'animate-spin' : ''}`} />
                        刷新模型列表
                      </button>
                    </span>
                    <select
                      value={settings.model_name || ''}
                      onChange={event => updateSetting('model_name', event.target.value)}
                      className="ios-input w-full rounded-md px-3 py-2.5 text-sm"
                    >
                      {Array.from(new Set([settings.model_name, ...availableModels].filter(Boolean))).map(model => (
                        <option key={model} value={model}>{model}</option>
                      ))}
                      {availableModels.length === 0 && !settings.model_name && (
                        <option value="">未获取到可用模型</option>
                      )}
                    </select>
                    {modelsError && <span className="mt-1 block text-xs text-amber-600">{modelsError}</span>}
                    {!modelsError && availableModels.length > 0 && (
                      <span className="mt-1 block text-xs text-gray-500">已加载 {availableModels.length} 个可用模型。</span>
                    )}
                  </label>
                  <label className="md:col-span-2">
                    <span className="mb-1.5 flex items-center justify-between gap-3 text-sm font-semibold text-gray-700">
                      <span className="flex items-center gap-2">
                        API Key
                        {settings.ai_env_overrides?.api_key && (
                          <span className="text-xs font-normal text-blue-600">已从 .env 加载</span>
                        )}
                      </span>
                      {settings.api_key_configured && !settings.api_key && (
                        <span className="flex items-center gap-1 text-xs font-medium text-emerald-700">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          已配置，留空保持不变
                        </span>
                      )}
                    </span>
                    <div className="relative">
                      <input
                        type={showApiKey ? 'text' : 'password'}
                        value={settings.api_key}
                        onChange={event => updateSetting('api_key', event.target.value)}
                        className="ios-input w-full rounded-md px-3 py-2.5 pr-10 text-sm"
                        placeholder={settings.api_key_configured ? '输入新密钥以替换' : '请输入 API Key'}
                        autoComplete="new-password"
                      />
                      <button
                        type="button"
                        onClick={() => setShowApiKey(value => !value)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-gray-500 hover:bg-gray-100"
                        title={showApiKey ? '隐藏密钥' : '显示密钥'}
                      >
                        {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </label>
                  <label className="md:col-span-2">
                    <span className="mb-1.5 block text-sm font-semibold text-gray-700">User-Agent</span>
                    <input
                      value={settings.user_agent ?? ''}
                      onChange={event => updateSetting('user_agent', event.target.value)}
                      className="ios-input w-full rounded-md px-3 py-2.5 text-sm"
                      placeholder="codex_cli_rs/0.0.0 (Hermes Agent)"
                    />
                    <span className="mt-1 block text-xs text-gray-500">部分 API 中转站（如 AgentRouter）通过 User-Agent 白名单检测客户端，留空使用默认值。</span>
                  </label>
                </div>
              </section>

              <section className="section-panel">
                <SectionHeader
                  title="全局回复风格"
                  description="适用于所有账号和商品，只描述语气、篇幅与表达习惯；商品业务规则请放到对应知识库。"
                  icon={MessageSquareText}
                />
                <div className="p-5">
                  <textarea value={replyStyle} onChange={event => setReplyStyle(event.target.value)} className="ios-input min-h-32 w-full resize-y rounded-md px-3 py-2.5 text-sm leading-6" placeholder={defaultReplyStyle} />
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                    <p className="text-xs leading-5 text-gray-500">示例：自然、友好、略带俏皮；一到两句短答；不夸张承诺、不连续使用表情。</p>
                    <button type="button" onClick={() => void handleSaveStyle()} disabled={styleSaving || !aiReplyEnabled} className="ios-btn-secondary flex items-center gap-2 rounded-md px-3 py-2 text-sm">
                      {styleSaving && <Loader2 className="h-4 w-4 animate-spin" />}保存回复风格
                    </button>
                  </div>
                </div>
              </section>

              <section className="section-panel">
                <SectionHeader
                  title="上下文对话"
                  description="控制单个买家会话中可用于连续回复的近期消息范围。"
                  icon={ShieldCheck}
                />
                <div className="grid gap-4 p-5 sm:grid-cols-2">
                  <label className="flex items-center justify-between gap-4 sm:col-span-2">
                    <span>
                      <span className="block text-sm font-semibold text-gray-700">记住近期对话</span>
                      <span className="mt-1 block text-xs leading-5 text-gray-500">
                        上下文按账号、会话和商品隔离，切换商品不会混入旧商品内容。
                      </span>
                    </span>
                    <input
                      type="checkbox"
                      checked={settings.context_enabled}
                      onChange={event => updateSetting('context_enabled', event.target.checked)}
                      className="h-5 w-5 shrink-0 accent-yellow-400"
                    />
                  </label>
                  <label>
                    <span className="mb-1.5 block text-sm font-semibold text-gray-700">记忆消息数</span>
                    <input
                      type="number"
                      min={2}
                      max={30}
                      disabled={!settings.context_enabled}
                      value={settings.context_message_limit}
                      onChange={event => updateSetting('context_message_limit', Number(event.target.value))}
                      className="ios-input w-full rounded-md px-3 py-2.5 text-sm disabled:bg-gray-100"
                    />
                  </label>
                  <label>
                    <span className="mb-1.5 block text-sm font-semibold text-gray-700">上下文有效期（分钟）</span>
                    <input
                      type="number"
                      min={5}
                      max={1440}
                      disabled={!settings.context_enabled}
                      value={settings.context_expire_minutes}
                      onChange={event => updateSetting('context_expire_minutes', Number(event.target.value))}
                      className="ios-input w-full rounded-md px-3 py-2.5 text-sm disabled:bg-gray-100"
                    />
                  </label>
                  <p className="text-xs leading-5 text-gray-500 sm:col-span-2">
                    付款、发货、退款、收货等系统事件不会交给大模型，将继续由订单状态和自动发货规则处理。
                  </p>
                </div>
              </section>
            </div>

            <aside className="space-y-5">
              <section className="section-panel">
                <SectionHeader
                  title="回复测试"
                  description="只生成文本，不会发送到闲鱼会话。"
                  icon={Play}
                />
                <div className="p-5">
                  <label className="mb-3 block">
                    <span className="mb-1.5 block text-xs font-semibold text-gray-600">测试商品（使用真实商品事实）</span>
                    <select
                      value={selectedItemId}
                      onChange={event => setSelectedItemId(event.target.value)}
                      className="ios-input w-full rounded-md px-3 py-2 text-sm"
                    >
                      {availableItems.map(item => (
                        <option key={item.item_id} value={item.item_id}>
                          {item.item_title || item.item_id} · {item.item_price || '未定价'}
                        </option>
                      ))}
                    </select>
                  </label>
                  <textarea
                    value={testMessage}
                    onChange={event => setTestMessage(event.target.value)}
                    className="ios-input min-h-24 w-full resize-y rounded-md px-3 py-2.5 text-sm"
                  />
                  <button
                    type="button"
                    onClick={handleTest}
                    disabled={testing || !settings.ai_enabled || !selectedItemId || !aiReplyEnabled}
                    className="ios-btn-primary mt-3 flex w-full items-center justify-center gap-2 rounded-md px-4 py-2.5 text-sm"
                  >
                    {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                    {testing ? '生成中' : '测试回复'}
                  </button>
                  {testReply && (
                    <div className="mt-4 border-l-4 border-yellow-400 bg-yellow-50 px-4 py-3 text-sm leading-6 text-gray-800">
                      {testReply}
                    </div>
                  )}
                </div>
              </section>

              <section className="section-panel p-5">
                <div className="flex items-start gap-3">
                  <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-700" />
                  <div>
                    <h2 className="text-sm font-bold text-gray-900">运行保护</h2>
                    <p className="mt-1 text-xs leading-5 text-gray-500">
                      密钥不会回传到浏览器；接口超时、空回复或格式异常时，系统会自动继续使用默认回复。
                    </p>
                  </div>
                </div>
              </section>
            </aside>
          </div>

        </>
      )}
    </div>
  );
};

export default AIReply;

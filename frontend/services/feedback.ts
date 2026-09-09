export type FeedbackType = 'success' | 'error' | 'warning' | 'info';

export interface FeedbackEventDetail {
  id: string;
  message: string;
  type: FeedbackType;
}

export interface ConfirmEventDetail {
  message: string;
  title: string;
  confirmLabel: string;
  cancelLabel: string;
  danger: boolean;
  resolve: (confirmed: boolean) => void;
}

export const FEEDBACK_EVENT = 'app:feedback';
export const CONFIRM_EVENT = 'app:confirm';

const inferType = (message: string): FeedbackType => {
  if (/失败|错误|异常|无法|error|fail/i.test(message)) return 'error';
  if (/警告|注意|请输入|请选择|warning/i.test(message)) return 'warning';
  if (/成功|完成|已新增|已保存|已删除|success/i.test(message)) return 'success';
  return 'info';
};

export const notify = (message: unknown, type?: FeedbackType) => {
  const normalized = String(message ?? '').trim();
  if (!normalized) return;

  window.dispatchEvent(new CustomEvent<FeedbackEventDetail>(FEEDBACK_EVENT, {
    detail: {
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      message: normalized,
      type: type || inferType(normalized),
    },
  }));
};

export const getApiErrorMessage = (error: unknown, fallback: string): string => {
  const candidate = error as {
    response?: { data?: { detail?: unknown } };
    message?: unknown;
  };
  const detail = candidate?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail.trim();
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === 'string' && message.trim()) return message.trim();
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map(item => item && typeof item === 'object' ? (item as { msg?: unknown }).msg : '')
      .filter((item): item is string => typeof item === 'string' && Boolean(item.trim()));
    if (messages.length) return messages.join('；');
  }
  const generic = typeof candidate?.message === 'string' ? candidate.message.trim() : '';
  return generic && !/status code \d+/i.test(generic) ? generic : fallback;
};

export const confirmAction = (
  message: string,
  options: Partial<Pick<ConfirmEventDetail, 'title' | 'confirmLabel' | 'cancelLabel' | 'danger'>> = {},
) => new Promise<boolean>((resolve) => {
  window.dispatchEvent(new CustomEvent<ConfirmEventDetail>(CONFIRM_EVENT, {
    detail: {
      message,
      title: options.title || '确认操作',
      confirmLabel: options.confirmLabel || '确认',
      cancelLabel: options.cancelLabel || '取消',
      danger: options.danger ?? true,
      resolve,
    },
  }));
});

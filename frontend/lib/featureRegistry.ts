import { FeatureKey } from '../types';

export interface FeatureUiMeta {
  pages: readonly string[];
  controls: readonly string[];
}

/**
 * UI 镜像只描述页面和控件归属，不复制后端默认值或运行时状态。
 */
export const FEATURE_UI_REGISTRY = {
  feature_items_enabled: { pages: ['items'], controls: ['item-list'] },
  item_sync_enabled: { pages: ['items'], controls: ['item-sync'] },
  auto_polish_enabled: { pages: ['items'], controls: ['item-polish'] },
  feature_orders_enabled: { pages: ['orders'], controls: ['order-list'] },
  order_sync_enabled: { pages: ['orders'], controls: ['order-sync'] },
  delivery_timeout_alert_enabled: { pages: ['orders'], controls: ['delivery-timeout-alert'] },
  auto_delivery_enabled: { pages: ['items', 'orders'], controls: ['delivery-config', 'manual-ship'] },
  feature_cards_enabled: { pages: ['cards'], controls: ['card-list'] },
  feature_buyer_interaction_enabled: { pages: ['buyer-interaction'], controls: ['rate', 'flower', 'thanks'] },
  feature_auto_reply_enabled: { pages: ['auto-reply'], controls: ['keyword-reply'] },
  feature_ai_reply_enabled: { pages: ['ai-reply'], controls: ['ai-settings', 'ai-test'] },
  feature_knowledge_base_enabled: { pages: ['knowledge-base'], controls: ['knowledge-crud', 'knowledge-preview'] },
  feature_product_automation_enabled: { pages: ['product-automation'], controls: ['product-automation'] },
  account_profile_auto_sync_enabled: { pages: ['accounts'], controls: ['profile-auto-sync'] },
  scheduled_token_refresh_enabled: { pages: ['accounts'], controls: ['token-refresh'] },
  browser_cookie_refresh_enabled: { pages: ['accounts'], controls: ['cookie-refresh'] },
} satisfies Record<FeatureKey, FeatureUiMeta>;

export const ALWAYS_VISIBLE_PAGE_IDS = [
  'dashboard',
  'accounts',
  'messages',
  'notifications',
  'settings',
  'about',
] as const;

export const FEATURE_PAGE_IDS = Array.from(
  new Set(Object.values(FEATURE_UI_REGISTRY).flatMap(meta => meta.pages)),
);

export const isFeaturePageEnabled = (
  snapshot: { effective: Record<FeatureKey, boolean> } | null,
  pageId: string,
): boolean => {
  if ((ALWAYS_VISIBLE_PAGE_IDS as readonly string[]).includes(pageId)) return true;
  const keys = (Object.keys(FEATURE_UI_REGISTRY) as FeatureKey[]).filter(key =>
    FEATURE_UI_REGISTRY[key].pages.includes(pageId),
  );
  return Boolean(snapshot && keys.length && keys.some(key => snapshot.effective[key]));
};

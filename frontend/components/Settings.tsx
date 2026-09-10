import React, { useEffect, useState } from 'react';
import {
  Database,
  Eye,
  EyeOff,
  KeyRound,
  Mail,
  Megaphone,
  RefreshCw,
  Save,
  Settings as SettingsIcon,
  ShieldCheck,
  Sparkles,
  SlidersHorizontal,
  UserRound,
  Zap,
} from 'lucide-react';

import {
  changePassword,
  createQuickPhrase,
  deleteQuickPhrase,
  getAvailableAIModels,
  getQuickPhrases,
  getSystemSettings,
  updateQuickPhrase,
  updateSystemSettings,
} from '../services/api';
import { notify } from '../services/feedback';
import { FeatureFlagDefinition, FeatureKey, QuickPhrase, SystemSettings } from '../types';
import { useFeatureFlags } from '../contexts/FeatureFlagsContext';
import {
  NoticeBanner,
  PageHeader,
  PageLoading,
  PageTabs,
  SectionHeader,
} from './ui';

type SettingsSection = 'general' | 'features' | 'ai' | 'email' | 'phrases' | 'notice';

const FEATURE_GROUP_LABELS: Record<string, string> = {
  page_modules: '页面模块',
  platform_background: '平台主动任务',
  message_actions: '消息动作',
};

/**
 * 把后端的开关值转成布尔。
 *
 * 后端统一把开关存成 'true' / 'false' 字符串。直接拿来当布尔用会踩坑：
 * 'false' 本身是 truthy，关掉的开关在界面上仍显示开启；再点一次取反得到的
 * 还是 false，于是开关一旦关闭就再也打不开。
 */
const toBool = (value: unknown, fallback = false): boolean => {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (!normalized) return fallback;
    return !['false', '0', 'no'].includes(normalized);
  }
  if (value === undefined || value === null) return fallback;
  return Boolean(value);
};

interface SettingToggleProps {
  title: string;
  description: string;
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
}

const SettingToggle: React.FC<SettingToggleProps> = ({
  title,
  description,
  checked,
  onChange,
  disabled = false,
}) => (
  <div className="flex items-center justify-between gap-4 border-b border-gray-100 px-4 py-3 last:border-b-0">
    <div className="min-w-0">
      <p className="text-sm font-bold text-gray-900">{title}</p>
      <p className="mt-1 text-xs leading-5 text-gray-500">{description}</p>
    </div>
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      disabled={disabled}
      className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
        checked ? 'bg-[var(--brand)]' : 'bg-gray-300'
      } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
    >
      <span
        className={`absolute left-1 top-1 h-4 w-4 rounded-full bg-white transition-transform ${
          checked ? 'translate-x-5' : ''
        }`}
      />
    </button>
  </div>
);

const Settings: React.FC = () => {
  const {
    snapshot: featureSnapshot,
    loading: featureLoading,
    updating: featureUpdating,
    error: featureError,
    runtimeApply,
    isAdmin,
    load: loadFeatureFlags,
    update: updateFeatureFlagsState,
  } = useFeatureFlags();
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeSection, setActiveSection] = useState<SettingsSection>('general');
  const [featureDraft, setFeatureDraft] = useState<Partial<Record<FeatureKey, boolean>> | null>(null);
  // 快捷短语：人工客服常用话术
  const [phrases, setPhrases] = useState<QuickPhrase[]>([]);
  const [phraseForm, setPhraseForm] = useState({ category: '默认', title: '', content: '' });

  const loadPhrases = () => {
    getQuickPhrases(true).then(setPhrases).catch(() => setPhrases([]));
  };

  useEffect(() => { loadPhrases(); }, []);

  useEffect(() => {
    if (featureSnapshot) setFeatureDraft({ ...featureSnapshot.configured });
  }, [featureSnapshot]);

  const handleAddPhrase = async () => {
    if (!phraseForm.title.trim() || !phraseForm.content.trim()) return;
    await createQuickPhrase(phraseForm.title.trim(), phraseForm.content.trim(), phraseForm.category.trim() || '默认');
    setPhraseForm({ category: phraseForm.category, title: '', content: '' });
    loadPhrases();
  };

  const handleTogglePhrase = async (phrase: QuickPhrase) => {
    await updateQuickPhrase(phrase.id, { enabled: !phrase.enabled });
    loadPhrases();
  };

  const handleDeletePhrase = async (id: number) => {
    await deleteQuickPhrase(id);
    loadPhrases();
  };

  const [showApiKey, setShowApiKey] = useState(false);
  const [showSmtpPassword, setShowSmtpPassword] = useState(false);

  // 修改登录密码。与页面顶部的「保存设置」互不影响：这里改的是当前账号的凭据，
  // 走的是独立接口，成功后立刻生效。
  const [passwordForm, setPasswordForm] = useState({ current: '', next: '', confirm: '' });
  const [showPasswordFields, setShowPasswordFields] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);

  const handleChangePassword = async () => {
    const { current, next, confirm } = passwordForm;
    if (!current || !next) {
      notify('请填写当前密码和新密码');
      return;
    }
    if (next.length < 6) {
      notify('新密码至少 6 位');
      return;
    }
    if (next !== confirm) {
      notify('两次输入的新密码不一致');
      return;
    }
    if (next === current) {
      notify('新密码不能与当前密码相同');
      return;
    }

    setChangingPassword(true);
    try {
      const result = await changePassword(current, next);
      // 后端对「当前密码错误」这类校验失败也返回 200，要看 success 字段
      if (result?.success === false) {
        notify(result.message || '密码修改失败');
        return;
      }
      setPasswordForm({ current: '', next: '', confirm: '' });
      notify('密码已修改，下次登录请使用新密码');
    } catch (error) {
      notify(`密码修改失败：${(error as Error).message}`);
    } finally {
      setChangingPassword(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = () => {
    setLoading(true);
    getSystemSettings().then((data) => {
      setSettings(data);
      // 管理员已经明确要求查看 .env API Key 时，首次加载直接显示实际值；
      // 仍可点击眼睛按钮重新隐藏。
      if (data.ai_env_overrides?.api_key) setShowApiKey(true);
    }).finally(() => setLoading(false));
  };

  const loadAvailableModels = async () => {
    setModelsLoading(true);
    setModelsError('');
    try {
      const result = await getAvailableAIModels();
      setAvailableModels(result.models || []);
      if (!result.models?.length) setModelsError('模型服务没有返回可用模型');
    } catch (error) {
      setModelsError(`获取模型列表失败：${(error as Error).message}`);
    } finally {
      setModelsLoading(false);
    }
  };

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      await updateSystemSettings(settings);
      notify('系统配置已保存');
    } catch (error) {
      notify(`保存失败：${(error as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveFeatures = async () => {
    if (!featureSnapshot || !featureDraft || !isAdmin) return;
    const changedFlags = Object.fromEntries(
      Object.entries(featureDraft).filter(([key, value]) => (
        value !== featureSnapshot.configured[key as FeatureKey]
      )),
    ) as Partial<Record<FeatureKey, boolean>>;
    if (Object.keys(changedFlags).length === 0) {
      notify('功能开关没有变化');
      return;
    }
    try {
      await updateFeatureFlagsState(changedFlags);
      notify('功能开关已保存');
    } catch (error) {
      // Context 保留旧 snapshot；draft 也保留，方便用户修正后重试。
      notify(`功能开关保存失败：${(error as Error).message}`);
    }
  };

  const featureGroups = featureSnapshot?.definitions.reduce<Record<string, FeatureFlagDefinition[]>>((groups, definition) => {
    (groups[definition.group] ||= []).push(definition);
    return groups;
  }, {}) || {};

  if (!settings) return <PageLoading label="正在加载系统设置" />;

  return (
    <div className="page-stack animate-fade-in">
      <PageHeader
        title="系统设置"
        description="配置管理端访问、商品同步、默认 AI 参数和邮件服务。"
        icon={SettingsIcon}
        actions={(
          <>
            <button
              type="button"
              onClick={() => (activeSection === 'features' ? void loadFeatureFlags() : loadSettings())}
              disabled={activeSection === 'features' ? featureLoading : loading}
              className="ios-btn-secondary flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm"
            >
              <RefreshCw className={`h-4 w-4 ${(activeSection === 'features' ? featureLoading : loading) ? 'animate-spin' : ''}`} />
              刷新
            </button>
            {activeSection === 'features' ? (
              <button
                type="button"
                onClick={() => void handleSaveFeatures()}
                disabled={!isAdmin || featureUpdating || !featureDraft}
                className="ios-btn-primary flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm disabled:opacity-60"
              >
                <Save className="h-4 w-4" />
                {featureUpdating ? '保存中' : '保存功能开关'}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => void handleSave()}
                disabled={saving}
                className="ios-btn-primary flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm"
              >
                <Save className="h-4 w-4" />
                {saving ? '保存中' : '保存设置'}
              </button>
            )}
          </>
        )}
      />

      <PageTabs
        value={activeSection}
        onChange={setActiveSection}
        ariaLabel="系统设置分区"
        items={[
          { id: 'general', label: '账号与同步', icon: UserRound },
          { id: 'features', label: '功能区', icon: SlidersHorizontal },
          { id: 'ai', label: '默认 AI 配置', icon: Sparkles },
          { id: 'email', label: '邮件服务', icon: Mail },
          { id: 'phrases', label: '快捷短语', icon: Zap },
          { id: 'notice', label: '公告与更新', icon: Megaphone },
        ]}
      />

      {activeSection === 'features' && (
        <div className="space-y-4">
          {featureError && (
            <NoticeBanner
              type="error"
              message={`${featureError}；可选业务已隐藏，聊天、账号和系统设置仍可使用。`}
            />
          )}
          {featureLoading && !featureSnapshot ? (
            <PageLoading label="正在加载功能开关" />
          ) : !featureSnapshot ? (
            <NoticeBanner type="warning" message="功能开关暂不可用，请刷新后重试。" />
          ) : (
            <>
              {!isAdmin && (
                <NoticeBanner type="info" message="当前账号只能查看功能状态，管理员可编辑并保存功能开关。" />
              )}
              {featureSnapshot.warnings.map((warning) => (
                <NoticeBanner key={warning} type="warning" message={warning} />
              ))}
              {runtimeApply && (
                <NoticeBanner
                  type={runtimeApply === 'failed' ? 'error' : runtimeApply === 'pending' ? 'warning' : 'success'}
                  message={`运行时应用状态：${runtimeApply}`}
                />
              )}
              {Object.entries(featureGroups).map(([group, definitions]) => (
                <section key={group} className="section-panel">
                  <SectionHeader
                    title={FEATURE_GROUP_LABELS[group] || group}
                    description="配置只改变开关状态，不会删除原有账号级参数或业务配置。"
                    icon={SlidersHorizontal}
                  />
                  {definitions.map((definition) => {
                    const checked = featureDraft?.[definition.key] === true;
                    const effective = featureSnapshot.effective[definition.key] === true;
                    const dependencyLabels = definition.depends_on
                      .map((key) => featureSnapshot.definitions.find(item => item.key === key)?.label || key)
                      .join('、');
                    return (
                      <React.Fragment key={definition.key}>
                        <SettingToggle
                          title={definition.label}
                          description={definition.description}
                          checked={checked}
                          onChange={() => setFeatureDraft(current => ({
                            ...(current || featureSnapshot.configured),
                            [definition.key]: !checked,
                          }))}
                          disabled={!isAdmin || featureUpdating}
                        />
                        <div className="border-b border-gray-100 px-4 pb-3 text-xs text-gray-500 last:border-b-0">
                          <span>configured：{checked ? '开启' : '关闭'} · effective：{effective ? '生效' : '未生效'}</span>
                          <span className="ml-3">风险：{definition.risk_level}</span>
                          {dependencyLabels && <span className="ml-3">依赖：{dependencyLabels}</span>}
                        </div>
                      </React.Fragment>
                    );
                  })}
                </section>
              ))}
            </>
          )}
        </div>
      )}

      {activeSection === 'general' && (
        <div className="grid gap-4 xl:grid-cols-2">
          <section className="section-panel">
            <SectionHeader
              title="访问与安全"
              description="控制后台注册入口、登录提示和验证码策略。"
              icon={ShieldCheck}
            />
            <SettingToggle
              title="允许用户注册"
              description="开启后允许新用户从登录页创建管理账号。"
              checked={toBool(settings.registration_enabled, true)}
              onChange={() => setSettings({
                ...settings,
                registration_enabled: !toBool(settings.registration_enabled, true),
              })}
            />
            <SettingToggle
              title="注册邮箱验证"
              description="要求注册时填写邮箱验证码。未配置下方「邮件服务」时请关闭，否则用户收不到验证码、无法完成注册。"
              checked={toBool(settings.email_verification_enabled, true)}
              onChange={() => setSettings({
                ...settings,
                email_verification_enabled: !toBool(settings.email_verification_enabled, true),
              })}
            />
            <SettingToggle
              title="显示默认登录信息"
              description="仅建议在本地调试环境显示默认账号提示。"
              checked={toBool(settings.show_default_login_info, true)}
              onChange={() => setSettings({
                ...settings,
                show_default_login_info: !toBool(settings.show_default_login_info, true),
              })}
            />
            <SettingToggle
              title="登录滑动验证码"
              description="账号密码登录前要求完成滑动验证。"
              checked={toBool(settings.login_captcha_enabled, true)}
              onChange={() => setSettings({
                ...settings,
                login_captcha_enabled: !toBool(settings.login_captcha_enabled, true),
              })}
            />
          </section>

          <section className="section-panel">
            <SectionHeader
              title="修改登录密码"
              description="修改当前登录账号的密码，保存后立即生效。"
              icon={KeyRound}
            />
            <div className="grid gap-4 p-4">
              <label>
                <span className="field-label">当前密码</span>
                <div className="relative">
                  <input
                    type={showPasswordFields ? 'text' : 'password'}
                    value={passwordForm.current}
                    onChange={e => setPasswordForm({ ...passwordForm, current: e.target.value })}
                    autoComplete="current-password"
                    placeholder="请输入当前密码"
                    className="ios-input w-full rounded-md px-3 py-2.5 pr-11 text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPasswordFields(!showPasswordFields)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                    aria-label={showPasswordFields ? '隐藏密码' : '显示密码'}
                  >
                    {showPasswordFields ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </label>

              <div className="grid gap-4 sm:grid-cols-2">
                <label>
                  <span className="field-label">新密码</span>
                  <input
                    type={showPasswordFields ? 'text' : 'password'}
                    value={passwordForm.next}
                    onChange={e => setPasswordForm({ ...passwordForm, next: e.target.value })}
                    autoComplete="new-password"
                    placeholder="至少 6 位"
                    className="ios-input w-full rounded-md px-3 py-2.5 text-sm"
                  />
                </label>
                <label>
                  <span className="field-label">确认新密码</span>
                  <input
                    type={showPasswordFields ? 'text' : 'password'}
                    value={passwordForm.confirm}
                    onChange={e => setPasswordForm({ ...passwordForm, confirm: e.target.value })}
                    autoComplete="new-password"
                    placeholder="再次输入新密码"
                    className="ios-input w-full rounded-md px-3 py-2.5 text-sm"
                  />
                </label>
              </div>

              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={() => void handleChangePassword()}
                  disabled={changingPassword}
                  className="ios-btn-primary flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm disabled:opacity-60"
                >
                  <KeyRound className="h-4 w-4" />
                  {changingPassword ? '修改中' : '修改密码'}
                </button>
              </div>
            </div>
          </section>

          <section className="section-panel">
            <SectionHeader
              title="商品同步"
              description="设置后台定时获取闲鱼商品的频率和单次范围。"
              icon={Database}
            />
            {featureSnapshot?.configured.item_sync_enabled === true && (
            <div className="grid gap-4 p-4 sm:grid-cols-2">
              <label>
                <span className="field-label">同步间隔（分钟）</span>
                <input
                  type="number"
                  value={Math.round((settings.item_sync_interval || 600) / 60)}
                  onChange={(event) => {
                    const minutes = parseInt(event.target.value, 10) || 10;
                    setSettings({ ...settings, item_sync_interval: minutes * 60 });
                  }}
                  className="ios-input w-full rounded-md px-3 py-2.5"
                  min="1"
                  max="1440"
                />
                <span className="mt-1 block text-xs text-gray-500">建议 10 至 60 分钟。</span>
              </label>
              <label>
                <span className="field-label">每次最多同步页数</span>
                <input
                  type="number"
                  value={settings.item_sync_max_pages || 5}
                  onChange={(event) => setSettings({
                    ...settings,
                    item_sync_max_pages: parseInt(event.target.value, 10) || 5,
                  })}
                  className="ios-input w-full rounded-md px-3 py-2.5"
                  min="1"
                  max="50"
                />
                <span className="mt-1 block text-xs text-gray-500">闲鱼接口通常每页返回 20 件商品。</span>
              </label>
            </div>
            )}
          </section>

          <section className="section-panel">
            <SectionHeader
              title="订单同步"
              description="定时从卖家端拉取订单，补齐监听离线期间产生的订单。"
              icon={Database}
            />
            {featureSnapshot?.configured.order_sync_enabled === true && (
            <div className="grid gap-4 p-4 sm:grid-cols-2">
              <label>
                <span className="field-label">同步间隔（分钟）</span>
                <input
                  type="number"
                  value={Math.round((settings.order_sync_interval || 1800) / 60)}
                  onChange={(event) => {
                    const minutes = parseInt(event.target.value, 10) || 30;
                    setSettings({ ...settings, order_sync_interval: minutes * 60 });
                  }}
                  className="ios-input w-full rounded-md px-3 py-2.5"
                  min="5"
                  max="1440"
                />
                <span className="mt-1 block text-xs text-gray-500">最低 5 分钟，建议 30 分钟。</span>
              </label>
            </div>
            )}
          </section>

          <section className="section-panel">
            <SectionHeader
              title="商品擦亮"
              description="定时擦亮商品重新获取搜索曝光，平台对每日次数有限制。"
              icon={Database}
            />
            {featureSnapshot?.configured.auto_polish_enabled === true && (
            <div className="grid gap-4 p-4 sm:grid-cols-2">
              <label>
                <span className="field-label">擦亮间隔（小时）</span>
                <input
                  type="number"
                  value={Math.round((settings.auto_polish_interval || 21600) / 3600)}
                  onChange={(event) => {
                    const hours = parseInt(event.target.value, 10) || 6;
                    setSettings({ ...settings, auto_polish_interval: hours * 3600 });
                  }}
                  className="ios-input w-full rounded-md px-3 py-2.5"
                  min="1"
                  max="24"
                />
                <span className="mt-1 block text-xs text-gray-500">最短 1 小时，建议 6 小时。</span>
              </label>
            </div>
            )}
          </section>

        </div>
      )}

      {activeSection === 'notice' && (
        <div className="grid gap-4 xl:grid-cols-2">
          <section className="section-panel">
            <SectionHeader
              title="公告与更新"
              description="填入你的公网 JSON 地址后，系统会定时拉取公告并检查新版本。"
              icon={Megaphone}
            />
            <SettingToggle
              title="启用公告与更新检查"
              description="关闭后不再拉取远端公告，也不提示新版本。"
              checked={settings.announcement_enabled !== 'false'}
              onChange={() => setSettings({
                ...settings,
                announcement_enabled: settings.announcement_enabled === 'false' ? 'true' : 'false',
              })}
            />
            <SettingToggle
              title="展示公告"
              description="关闭后顶部横幅和「关于」页都不再显示公告内容，仍会正常检查新版本。"
              checked={toBool(settings.announcement_show_notice, true)}
              onChange={() => setSettings({
                ...settings,
                announcement_show_notice: !toBool(settings.announcement_show_notice, true),
              })}
            />
            <SettingToggle
              title="展示版本更新提示"
              description="关闭后不再弹出新版本横幅，公告照常显示。适合不希望团队成员自行升级的场景。"
              checked={toBool(settings.announcement_show_update, true)}
              onChange={() => setSettings({
                ...settings,
                announcement_show_update: !toBool(settings.announcement_show_update, true),
              })}
            />
            <div className="px-4 py-3">
              <label className="field-label">公告 JSON 地址</label>
              <input
                type="url"
                value={settings.announcement_source_url || ''}
                onChange={e => setSettings({
                  ...settings,
                  announcement_source_url: e.target.value,
                })}
                placeholder="https://example.com/announcement.json（留空表示未配置）"
                className="ios-input mt-1 w-full rounded-md px-3 py-2 text-sm"
              />
              <p className="mt-1.5 text-xs text-gray-500">
                留空则使用官方公告源，可填入自建地址替换。
                后端每 10 分钟拉取一次并缓存；远端不可用时沿用上次结果。
                在「关于」页可手动点「检查更新」立即刷新。
              </p>
            </div>
          </section>
        </div>
      )}

      {activeSection === 'phrases' && (
        <section className="section-panel">
          <SectionHeader
            title="快捷短语"
            description="人工客服常用话术，在消息管理页可一键插入到输入框。"
            icon={Zap}
          />
          <div className="grid gap-3 p-4 sm:grid-cols-[140px_200px_1fr_auto]">
            <input
              value={phraseForm.category}
              onChange={(e) => setPhraseForm({ ...phraseForm, category: e.target.value })}
              placeholder="分类"
              className="ios-input rounded-md px-3 py-2.5"
            />
            <input
              value={phraseForm.title}
              onChange={(e) => setPhraseForm({ ...phraseForm, title: e.target.value })}
              placeholder="标题"
              className="ios-input rounded-md px-3 py-2.5"
            />
            <input
              value={phraseForm.content}
              onChange={(e) => setPhraseForm({ ...phraseForm, content: e.target.value })}
              placeholder="话术内容"
              className="ios-input rounded-md px-3 py-2.5"
            />
            <button
              type="button"
              onClick={() => void handleAddPhrase()}
              disabled={!phraseForm.title.trim() || !phraseForm.content.trim()}
              className="ios-btn-primary rounded-md px-4 py-2.5 text-sm disabled:opacity-60"
            >
              添加
            </button>
          </div>
          <div className="divide-y divide-gray-100 border-t border-gray-100">
            {phrases.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-gray-500">还没有快捷短语</p>
            ) : (
              phrases.map((phrase) => (
                <div key={phrase.id} className="flex items-center gap-3 px-4 py-3">
                  <span className="w-20 shrink-0 text-xs text-gray-500">{phrase.category}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-gray-800">{phrase.title}</p>
                    <p className="truncate text-xs text-gray-500">{phrase.content}</p>
                  </div>
                  <span className="shrink-0 text-xs text-gray-400">用了 {phrase.use_count} 次</span>
                  <button
                    type="button"
                    onClick={() => void handleTogglePhrase(phrase)}
                    className="shrink-0 text-xs text-blue-600 hover:underline"
                  >
                    {phrase.enabled ? '停用' : '启用'}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDeletePhrase(phrase.id)}
                    className="shrink-0 text-xs text-red-500 hover:underline"
                  >
                    删除
                  </button>
                </div>
              ))
            )}
          </div>
        </section>
      )}

      {activeSection === 'ai' && (
        <section className="section-panel">
          <SectionHeader
            title="默认 AI 配置"
            description="作为账号未单独配置时使用的全局模型与回复内容。"
            icon={Sparkles}
          />
          <div className="grid gap-4 p-4 lg:grid-cols-2">
            <label>
              <span className="field-label flex items-center gap-2">
                API 地址
                {settings.ai_env_overrides?.base_url && (
                  <span className="font-normal text-xs text-blue-600">已从 .env 加载</span>
                )}
              </span>
              <input
                type="text"
                value={settings.ai_api_url || ''}
                onChange={(event) => setSettings({ ...settings, ai_api_url: event.target.value })}
                className="ios-input w-full rounded-md px-3 py-2.5 text-sm"
                placeholder="https://api.openai.com/v1"
              />
              <span className="mt-1 block text-xs text-gray-500">
                填写兼容 OpenAI 协议的服务根地址，无需补全 `/chat/completions`。
              </span>
            </label>

            <label>
              <span className="field-label flex items-center gap-2">
                API Key
                {settings.ai_env_overrides?.api_key && (
                  <span className="font-normal text-xs text-blue-600">已从 .env 加载</span>
                )}
              </span>
              <div className="relative">
                <input
                type={showApiKey ? 'text' : 'password'}
                value={settings.ai_api_key || ''}
                onChange={(event) => setSettings({ ...settings, ai_api_key: event.target.value })}
                className="ios-input w-full rounded-md px-3 py-2.5 pr-11 font-mono text-sm"
                  placeholder="sk-..."
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                  aria-label={showApiKey ? '隐藏 API Key' : '显示 API Key'}
                >
                  {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </label>

            <label>
              <span className="field-label flex items-center justify-between gap-2">
                <span className="flex items-center gap-2">
                  默认模型
                  {settings.ai_env_overrides?.model_name && (
                    <span className="font-normal text-xs text-blue-600">已从 .env 加载</span>
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
                value={settings.ai_model || ''}
                onChange={(event) => setSettings({ ...settings, ai_model: event.target.value })}
                className="ios-input w-full rounded-md px-3 py-2.5"
              >
                {Array.from(new Set([settings.ai_model, ...availableModels].filter(Boolean))).map((model) => (
                  <option key={model} value={model}>{model}</option>
                ))}
                {availableModels.length === 0 && !settings.ai_model && (
                  <option value="">未获取到可用模型</option>
                )}
              </select>
              {modelsError && <span className="mt-1 block text-xs text-amber-600">{modelsError}</span>}
              {!modelsError && availableModels.length > 0 && (
                <span className="mt-1 block text-xs text-gray-500">已加载 {availableModels.length} 个可用模型。</span>
              )}
            </label>

            {Object.keys(settings.ai_env_overrides || {}).length > 0 && (
              <div className="lg:col-span-2 rounded-md border border-blue-200 bg-blue-50 p-3 text-xs text-blue-800">
                当前值来自 `.env` 默认配置；你可以直接在页面修改并保存，保存后的页面配置会覆盖 `.env` 默认值。
              </div>
            )}

            <label className="lg:col-span-2">
              <span className="field-label">默认自动回复内容</span>
              <textarea
                className="ios-input min-h-28 w-full resize-y rounded-md px-3 py-2.5 text-sm"
                value={settings.default_reply || ''}
                onChange={(event) => setSettings({ ...settings, default_reply: event.target.value })}
                placeholder="设置默认的自动回复内容..."
              />
            </label>

            <div className="lg:col-span-2">
              <NoticeBanner
                type="info"
                message="常用兼容服务包括阿里云 DashScope 和 OpenAI。API Key 可来自 .env 或当前系统配置。"
              />
            </div>
          </div>
        </section>
      )}

      {activeSection === 'email' && (
        <section className="section-panel">
          <SectionHeader
            title="SMTP 邮件服务"
            description="用于发送注册验证码和系统邮件通知。"
            icon={Mail}
          />
          <div className="grid gap-4 p-4 lg:grid-cols-2">
            <label>
              <span className="field-label">SMTP 服务器</span>
              <input
                type="text"
                value={settings.smtp_server || ''}
                onChange={(event) => setSettings({ ...settings, smtp_server: event.target.value })}
                placeholder="smtp.qq.com"
                className="ios-input w-full rounded-md px-3 py-2.5 text-sm"
              />
            </label>

            <label>
              <span className="field-label">SMTP 端口</span>
              <input
                type="number"
                value={settings.smtp_port || 587}
                onChange={(event) => setSettings({
                  ...settings,
                  smtp_port: parseInt(event.target.value, 10),
                })}
                placeholder="587"
                className="ios-input w-full rounded-md px-3 py-2.5 text-sm"
              />
            </label>

            <label>
              <span className="field-label">发件邮箱</span>
              <input
                type="email"
                value={settings.smtp_user || ''}
                onChange={(event) => setSettings({ ...settings, smtp_user: event.target.value })}
                placeholder="your-email@qq.com"
                className="ios-input w-full rounded-md px-3 py-2.5 text-sm"
              />
            </label>

            <label>
              <span className="field-label">邮箱密码或授权码</span>
              <div className="relative">
                <input
                  type={showSmtpPassword ? 'text' : 'password'}
                  value={settings.smtp_password || ''}
                  onChange={(event) => setSettings({ ...settings, smtp_password: event.target.value })}
                  placeholder="输入密码或授权码"
                  className="ios-input w-full rounded-md px-3 py-2.5 pr-11 text-sm"
                />
                <button
                  type="button"
                  onClick={() => setShowSmtpPassword(!showSmtpPassword)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                  aria-label={showSmtpPassword ? '隐藏邮箱授权码' : '显示邮箱授权码'}
                >
                  {showSmtpPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              <span className="mt-1 block text-xs text-gray-500">QQ 邮箱等服务通常要求填写授权码。</span>
            </label>

            <label className="lg:col-span-2">
              <span className="field-label">发件人显示名</span>
              <input
                type="text"
                value={settings.smtp_from || ''}
                onChange={(event) => setSettings({ ...settings, smtp_from: event.target.value })}
                placeholder="闲鱼自动回复系统"
                className="ios-input w-full rounded-md px-3 py-2.5 text-sm"
              />
            </label>
          </div>
        </section>
      )}
    </div>
  );
};

export default Settings;

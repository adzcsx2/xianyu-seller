import React, { useEffect, useMemo, useState } from 'react';
import { Bot, Loader2, Save, Send, X } from 'lucide-react';
import {
  KnowledgeBaseDetail,
  KnowledgeFact,
  KnowledgeQAEntry,
  KnowledgeRule,
  KnowledgeSource,
} from '../types';
import {
  askKnowledgeBase,
  createKnowledgeContent,
  deleteKnowledgeContent,
  getKnowledgeBase,
  updateKnowledgeBase,
  updateKnowledgeContent,
} from '../services/api';
import { confirmAction, getApiErrorMessage, notify } from '../services/feedback';

type Kind = 'facts' | 'sources' | 'rules' | 'qa-entries';
type Content = KnowledgeFact | KnowledgeSource | KnowledgeRule | KnowledgeQAEntry;
type Draft = Partial<Content> & Record<string, unknown>;

interface KnowledgeBaseEditorModalProps {
  baseId: string;
  aiConfigAccountId: string;
  onClose: () => void;
  onSaved?: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}

const tabs: Array<{ kind: Kind; label: string }> = [
  { kind: 'facts', label: '买家可见事实' },
  { kind: 'sources', label: '来源引用' },
  { kind: 'rules', label: '内部规则' },
  { kind: 'qa-entries', label: '公开问答条目' },
];

const ruleTypes = [
  { value: 'fixed_reply', label: '固定回复' },
  { value: 'topic_refusal', label: '敏感话题拒答' },
  { value: 'pricing_policy', label: '价格策略' },
  { value: 'bargain_policy', label: '议价策略' },
  { value: 'model_instruction', label: '模型补充说明' },
  { value: 'output_guard', label: '输出防护' },
];

const mutableFields: Record<Kind, string[]> = {
  facts: ['fact_key', 'category', 'title', 'content', 'source_ids', 'priority', 'enabled'],
  sources: ['source_key', 'title', 'reference', 'url', 'notes'],
  rules: ['rule_key', 'name', 'rule_type', 'intent', 'matchers', 'instruction', 'response', 'config_json', 'source_ids', 'priority', 'enabled'],
  'qa-entries': ['qa_key', 'category', 'questions', 'keywords', 'answer', 'source_ids', 'priority', 'enabled'],
};

const emptyDraft = (kind: Kind): Draft => {
  if (kind === 'facts') return { fact_key: '', category: 'product', title: '', content: '', source_ids: [], priority: 0, enabled: true };
  if (kind === 'sources') return { source_key: '', title: '', reference: '', url: '', notes: '' };
  if (kind === 'rules') return { rule_key: '', name: '', rule_type: 'model_instruction', intent: 'general', matchers: [], instruction: '', response: '', config_json: {}, source_ids: [], priority: 0, enabled: true };
  return { qa_key: '', category: 'general', questions: [], keywords: [], answer: '', source_ids: [], priority: 0, enabled: true };
};

const asLines = (value: unknown) => Array.isArray(value) ? value.join('\n') : String(value || '');
const configField = (value: unknown, key: string) => value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>)[key] : '';

const KnowledgeBaseEditorModal: React.FC<KnowledgeBaseEditorModalProps> = ({
  baseId,
  aiConfigAccountId,
  onClose,
  onSaved,
  onDirtyChange,
}) => {
  const [base, setBase] = useState<KnowledgeBaseDetail | null>(null);
  const [tab, setTab] = useState<Kind>('facts');
  const [editingMeta, setEditingMeta] = useState({ name: '', description: '' });
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [metaDirty, setMetaDirty] = useState(false);
  const [contentDirty, setContentDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [answerModel, setAnswerModel] = useState('');
  const [asking, setAsking] = useState(false);

  const contents = useMemo<Content[]>(() => {
    if (!base) return [];
    if (tab === 'facts') return base.facts;
    if (tab === 'sources') return base.sources;
    if (tab === 'rules') return base.rules;
    return base.qa_entries;
  }, [base, tab]);

  useEffect(() => {
    onDirtyChange?.(metaDirty || contentDirty);
  }, [contentDirty, metaDirty, onDirtyChange]);

  const reload = async (preserveMeta = false) => {
    const data = await getKnowledgeBase(baseId);
    setBase(data);
    if (!preserveMeta) {
      setEditingMeta({ name: data.name, description: data.description || '' });
      setMetaDirty(false);
    }
    return data;
  };

  useEffect(() => {
    setLoading(true);
    setDraft(null);
    setEditingId(null);
    setContentDirty(false);
    reload()
      .catch(error => notify(error instanceof Error ? error.message : '知识库加载失败', 'error'))
      .finally(() => setLoading(false));
    // baseId identifies the modal instance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseId]);

  const confirmDiscardContent = async () => !contentDirty || confirmAction(
    '当前条目尚未保存，确定放弃修改吗？',
    { title: '放弃未保存条目', confirmLabel: '放弃修改', danger: true },
  );

  const resetContentDraft = () => {
    setEditingId(null);
    setDraft(null);
    setContentDirty(false);
  };

  const requestTabChange = async (nextTab: Kind) => {
    if (nextTab === tab) return;
    if (!(await confirmDiscardContent())) return;
    resetContentDraft();
    setTab(nextTab);
  };

  const startAdd = async () => {
    if (!(await confirmDiscardContent())) return;
    setEditingId(null);
    setDraft(emptyDraft(tab));
    setContentDirty(false);
  };

  const startEdit = async (entry: Content) => {
    if (!(await confirmDiscardContent())) return;
    setEditingId(entry.id);
    setDraft({ ...entry });
    setContentDirty(false);
  };

  const change = (key: string, value: unknown) => {
    setDraft(current => ({ ...(current || emptyDraft(tab)), [key]: value }));
    setContentDirty(true);
  };

  const changeRuleType = (ruleType: string) => {
    setDraft(current => ({
      ...(current || emptyDraft('rules')),
      rule_type: ruleType,
      instruction: ruleType === 'model_instruction' ? String(current?.instruction || '') : '',
      response: ['fixed_reply', 'topic_refusal'].includes(ruleType) ? String(current?.response || '') : '',
      config_json: {},
    }));
    setContentDirty(true);
  };

  const changeConfig = (key: string, value: unknown) => {
    const config = draft?.config_json && typeof draft.config_json === 'object' && !Array.isArray(draft.config_json)
      ? draft.config_json as Record<string, unknown>
      : {};
    change('config_json', { ...config, [key]: value });
  };

  const saveMeta = async () => {
    if (!base || !editingMeta.name.trim()) return;
    setSaving(true);
    try {
      const updated = await updateKnowledgeBase(base.id, base.version, {
        name: editingMeta.name.trim(),
        description: editingMeta.description.trim(),
      });
      setBase(current => current ? { ...current, ...updated } : current);
      setMetaDirty(false);
      onSaved?.();
      notify('知识库信息已保存', 'success');
    } catch (error: any) {
      notify(error?.response?.status === 409 ? '知识库版本已变化，请重新加载' : (error instanceof Error ? error.message : '保存失败'), 'error');
    } finally {
      setSaving(false);
    }
  };

  const contentPayload = () => {
    const payload: Record<string, unknown> = {};
    for (const key of mutableFields[tab]) {
      if (draft && key in draft) payload[key] = draft[key];
    }
    for (const key of ['questions', 'keywords', 'matchers']) {
      if (key in payload && typeof payload[key] === 'string') {
        payload[key] = String(payload[key]).split('\n').map(value => value.trim()).filter(Boolean);
      }
    }
    return payload;
  };

  const saveContent = async () => {
    if (!base || !draft) return;
    setSaving(true);
    try {
      const payload = contentPayload();
      if (editingId) await updateKnowledgeContent(base.id, tab, editingId, base.version, payload);
      else await createKnowledgeContent(base.id, tab, base.version, payload);
      await reload(true);
      resetContentDraft();
      onSaved?.();
      notify('知识库内容已保存', 'success');
    } catch (error: any) {
      notify(error?.response?.status === 409 ? '版本已变化或键名重复，请重新加载' : getApiErrorMessage(error, '保存内容失败'), 'error');
    } finally {
      setSaving(false);
    }
  };

  const askCurrentKnowledgeBase = async () => {
    const normalized = question.trim();
    if (!base || !normalized || !aiConfigAccountId || asking) return;
    setAsking(true);
    setAnswer('');
    try {
      const result = await askKnowledgeBase(base.id, aiConfigAccountId, normalized);
      setAnswer(result.answer);
      setAnswerModel(result.model_name);
    } catch (error) {
      notify(getApiErrorMessage(error, '知识库问答失败'), 'error');
    } finally {
      setAsking(false);
    }
  };

  const removeContent = async (entry: Content) => {
    if (!base || saving || !(await confirmDiscardContent())) return;
    const label = ('name' in entry && entry.name) || ('title' in entry && entry.title) || entry.id;
    if (!(await confirmAction(`确认删除“${label}”吗？`, { title: '删除知识库内容', confirmLabel: '确定删除', danger: true }))) return;
    setSaving(true);
    try {
      await deleteKnowledgeContent(base.id, tab, entry.id, base.version);
      await reload(true);
      resetContentDraft();
      onSaved?.();
      notify('内容已删除', 'success');
    } catch (error: any) {
      notify(error?.response?.status === 409 ? '版本已变化，请重新加载' : (error instanceof Error ? error.message : '删除失败'), 'error');
    } finally {
      setSaving(false);
    }
  };

  const requestClose = async () => {
    if (saving) return;
    if ((metaDirty || contentDirty) && !(await confirmAction(
      '当前编辑内容尚未保存，确定关闭吗？',
      { title: '放弃编辑', confirmLabel: '关闭', danger: true },
    ))) return;
    onDirtyChange?.(false);
    onClose();
  };

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') void requestClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  });

  const sourceIds = Array.isArray(draft?.source_ids) ? draft.source_ids as string[] : [];
  const toggleSource = (sourceId: string) => change(
    'source_ids',
    sourceIds.includes(sourceId) ? sourceIds.filter(id => id !== sourceId) : [...sourceIds, sourceId],
  );

  if (loading) return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"><div className="rounded-xl bg-[var(--surface)] p-6"><Loader2 className="h-5 w-5 animate-spin" /></div></div>;
  if (!base) return null;

  const ruleType = String(draft?.rule_type || 'model_instruction');

  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true" aria-labelledby="knowledge-editor-title">
    <div className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl bg-[var(--surface)] shadow-xl">
      <header className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4"><div><h2 id="knowledge-editor-title" className="text-lg font-bold">{base.name}</h2><p className="text-xs text-[var(--text-muted)]">版本 {base.version} · 全局知识库</p></div><button type="button" onClick={() => void requestClose()} className="rounded-md p-2 hover:bg-[var(--surface-hover)]" aria-label="关闭"><X className="h-5 w-5" /></button></header>
      <div className="grid min-h-0 flex-1 gap-0 md:grid-cols-[220px_1fr]">
        <aside className="border-b border-[var(--border)] p-3 md:border-b-0 md:border-r">
          <div className="mb-3 rounded-lg bg-[var(--surface-hover)] p-3"><label className="block text-xs font-semibold">名称<input value={editingMeta.name} onChange={event => { setEditingMeta(current => ({ ...current, name: event.target.value })); setMetaDirty(true); }} className="ios-input mt-1 w-full rounded-md px-2 py-1.5 text-sm" /></label><label className="mt-2 block text-xs font-semibold">描述<textarea value={editingMeta.description} onChange={event => { setEditingMeta(current => ({ ...current, description: event.target.value })); setMetaDirty(true); }} className="ios-input mt-1 w-full rounded-md px-2 py-1.5 text-sm" /></label><button type="button" onClick={() => void saveMeta()} disabled={saving || !metaDirty || !editingMeta.name.trim()} className="ios-btn-secondary mt-2 flex w-full items-center justify-center gap-1 rounded-md px-2 py-1.5 text-xs"><Save className="h-3.5 w-3.5" />保存信息</button></div>
          {tabs.map(item => <button key={item.kind} type="button" disabled={saving} onClick={() => void requestTabChange(item.kind)} className={`mb-1 w-full rounded-md px-3 py-2 text-left text-sm disabled:opacity-50 ${tab === item.kind ? 'bg-brand-100 font-bold text-brand-ink' : 'hover:bg-[var(--surface-hover)]'}`}>{item.label}<span className="float-right text-xs text-[var(--text-muted)]">{item.kind === 'facts' ? base.facts.length : item.kind === 'sources' ? base.sources.length : item.kind === 'rules' ? base.rules.length : base.qa_entries.length}</span></button>)}
        </aside>
        <main className="min-h-0 overflow-y-auto p-5">
          <section className="mb-5 rounded-xl border border-brand-200 bg-brand-50/40 p-4" aria-labelledby="knowledge-ask-title">
            <div className="flex items-start gap-3"><span className="rounded-lg bg-brand-100 p-2 text-brand-ink"><Bot className="h-5 w-5" /></span><div><h3 id="knowledge-ask-title" className="font-bold">知识库问答</h3><p className="mt-1 text-xs text-[var(--text-muted)]">使用页面顶部所选账号的 AI 配置，只根据当前打开知识库中已启用的事实、公开问答和内部规则回答。</p></div></div>
            <textarea value={question} onChange={event => setQuestion(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void askCurrentKnowledgeBase(); } }} disabled={asking} className="ios-input mt-3 min-h-20 w-full rounded-md px-3 py-2 text-sm" placeholder="输入要向当前知识库提问的问题；Enter 发送，Shift+Enter 换行" aria-label="向当前知识库提问" />
            <div className="mt-3 flex items-center justify-between gap-3"><span className="text-xs text-[var(--text-muted)]">{aiConfigAccountId ? '不会读取其他知识库，也不会发送来源备注。' : '请先在知识库页面顶部选择一个已配置 AI 的账号。'}</span><button type="button" onClick={() => void askCurrentKnowledgeBase()} disabled={asking || !question.trim() || !aiConfigAccountId} className="ios-btn-primary flex shrink-0 items-center gap-1 rounded-md px-3 py-2 text-sm">{asking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}{asking ? '回答中' : '提问'}</button></div>
            {answer && <div className="mt-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3" role="status"><div className="flex items-center justify-between gap-3"><span className="text-xs font-semibold text-[var(--text-muted)]">AI 回答</span>{answerModel && <span className="text-xs text-[var(--text-soft)]">{answerModel}</span>}</div><p className="mt-2 whitespace-pre-wrap text-sm leading-6">{answer}</p></div>}
          </section>
          <div className="mb-4 flex items-center justify-between gap-3"><div><h3 className="font-bold">{tabs.find(item => item.kind === tab)?.label}</h3><p className="text-xs text-[var(--text-muted)]">可单独保存、停用或删除条目；保存时使用版本校验。</p></div><button type="button" onClick={() => void startAdd()} disabled={saving} className="ios-btn-primary rounded-md px-3 py-2 text-sm">新增条目</button></div>
          <div className="space-y-2">{contents.map(entry => <div key={entry.id} className="rounded-xl border border-[var(--border)] p-3"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="font-semibold">{('name' in entry && entry.name) || ('title' in entry && entry.title) || ('rule_key' in entry && entry.rule_key) || ('qa_key' in entry && entry.qa_key)}</p><p className="mt-1 line-clamp-2 text-sm text-[var(--text-muted)]">{('content' in entry && entry.content) || ('answer' in entry && entry.answer) || ('reference' in entry && entry.reference) || ('instruction' in entry && entry.instruction) || '暂无内容'}</p></div><div className="flex shrink-0 gap-2"><button type="button" disabled={saving} onClick={() => void startEdit(entry)} className="ios-btn-secondary rounded-md px-2 py-1 text-xs">编辑</button><button type="button" disabled={saving} onClick={() => void removeContent(entry)} className="rounded-md px-2 py-1 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50">删除</button></div></div></div>)}{!contents.length && <p className="rounded-xl border border-dashed border-[var(--border)] px-4 py-10 text-center text-sm text-[var(--text-muted)]">暂无条目，点击“新增条目”开始维护。</p>}</div>

          {draft && <section className="mt-5 rounded-xl border border-brand-200 bg-brand-50/40 p-4">
            <div className="grid gap-3 md:grid-cols-2">
              {tab === 'facts' && <><Field label="事实键" value={draft.fact_key} onChange={value => change('fact_key', value)} /><Field label="分类" value={draft.category} onChange={value => change('category', value)} /><Field label="标题" value={draft.title} onChange={value => change('title', value)} /><Field label="优先级" type="number" value={draft.priority} onChange={value => change('priority', Number(value))} /><TextAreaField label="买家可见内容" value={draft.content} onChange={value => change('content', value)} full /></>}
              {tab === 'sources' && <><Field label="来源键" value={draft.source_key} onChange={value => change('source_key', value)} /><Field label="标题" value={draft.title} onChange={value => change('title', value)} /><Field label="引用说明" value={draft.reference} onChange={value => change('reference', value)} /><Field label="URL（可选）" value={draft.url} onChange={value => change('url', value)} /><TextAreaField label="备注" value={draft.notes} onChange={value => change('notes', value)} full /></>}
              {tab === 'rules' && <><Field label="规则键" value={draft.rule_key} onChange={value => change('rule_key', value)} /><Field label="规则名称" value={draft.name} onChange={value => change('name', value)} /><label className="block text-xs font-semibold">规则类型<select value={ruleType} onChange={event => changeRuleType(event.target.value)} className="ios-input mt-1 w-full rounded-md px-2.5 py-2 text-sm">{ruleTypes.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><Field label="意图" value={draft.intent} onChange={value => change('intent', value)} /><TextAreaField label="匹配词（每行一个）" value={asLines(draft.matchers)} onChange={value => change('matchers', value.split('\n').map(item => item.trim()).filter(Boolean))} />{ruleType === 'model_instruction' && <TextAreaField label="内部指令" value={draft.instruction} onChange={value => change('instruction', value)} full />}{['fixed_reply', 'topic_refusal'].includes(ruleType) && <TextAreaField label="固定回复" value={draft.response} onChange={value => change('response', value)} full />}{ruleType === 'pricing_policy' && <><Field label="原价" value={configField(draft.config_json, 'original_price')} onChange={value => changeConfig('original_price', value)} /><Field label="当前价" value={configField(draft.config_json, 'current_price')} onChange={value => changeConfig('current_price', value)} /><Field label="活动说明" value={configField(draft.config_json, 'promotion_label')} onChange={value => changeConfig('promotion_label', value)} /><Field label="活动结束时间（可选）" value={configField(draft.config_json, 'promotion_end')} onChange={value => changeConfig('promotion_end', value || null)} /></>}{ruleType === 'bargain_policy' && <><Field label="最大优惠比例" type="number" value={configField(draft.config_json, 'max_discount_percent')} onChange={value => changeConfig('max_discount_percent', Number(value))} /><Field label="最大优惠金额" value={configField(draft.config_json, 'max_discount_amount')} onChange={value => changeConfig('max_discount_amount', value)} /><Field label="最大议价轮数" type="number" value={configField(draft.config_json, 'max_rounds')} onChange={value => changeConfig('max_rounds', Number(value))} /><label className="block text-xs font-semibold">底价方式<select value={String(configField(draft.config_json, 'floor_mode') || 'current_price')} onChange={event => changeConfig('floor_mode', event.target.value)} className="ios-input mt-1 w-full rounded-md px-2.5 py-2 text-sm"><option value="current_price">当前商品价格</option><option value="fixed">固定底价</option></select></label>{configField(draft.config_json, 'floor_mode') === 'fixed' && <Field label="固定底价" value={configField(draft.config_json, 'floor_price')} onChange={value => changeConfig('floor_price', value)} />}</>}{ruleType === 'output_guard' && <><TextAreaField label="未被询问时禁止输出（每行一个）" value={asLines(configField(draft.config_json, 'forbidden_unless_asked'))} onChange={value => changeConfig('forbidden_unless_asked', value.split('\n').map(item => item.trim()).filter(Boolean))} full /><label className="block text-xs font-semibold">拦截后的回复<select value={String(configField(draft.config_json, 'fallback_mode') || 'human_confirmation')} onChange={event => changeConfig('fallback_mode', event.target.value)} className="ios-input mt-1 w-full rounded-md px-2.5 py-2 text-sm"><option value="human_confirmation">转人工确认</option><option value="top_match">使用最佳知识答案</option></select></label></>}</>}
              {tab === 'qa-entries' && <>{editingId ? <div className="text-xs"><p className="font-semibold">内部标识</p><p className="mt-1 rounded-md bg-[var(--surface-hover)] px-2.5 py-2 font-mono">{String(draft.qa_key || '')}</p></div> : <div className="text-xs"><p className="font-semibold">内部标识</p><p className="mt-1 rounded-md bg-[var(--surface-hover)] px-2.5 py-2 text-[var(--text-muted)]">留空后由系统自动生成</p></div>}<Field label="分类" value={draft.category} onChange={value => change('category', value)} /><TextAreaField label="问题（每行一个）" value={asLines(draft.questions)} onChange={value => change('questions', value.split('\n').map(item => item.trim()).filter(Boolean))} /><TextAreaField label="关键词（每行一个）" value={asLines(draft.keywords)} onChange={value => change('keywords', value.split('\n').map(item => item.trim()).filter(Boolean))} /><TextAreaField label="公开答案" value={draft.answer} onChange={value => change('answer', value)} full /></>}
            </div>
            {tab !== 'sources' && <><label className="mt-3 inline-flex items-center gap-2 text-xs font-semibold"><input type="checkbox" checked={draft.enabled !== false} onChange={event => change('enabled', event.target.checked)} />启用此条目</label><div className="mt-3"><p className="mb-1 text-xs font-semibold">来源引用（可选）</p><div className="flex flex-wrap gap-2">{base.sources.map(source => <label key={source.id} className="flex items-center gap-1 text-xs"><input type="checkbox" checked={sourceIds.includes(source.id)} onChange={() => toggleSource(source.id)} />{source.title}</label>)}{!base.sources.length && <span className="text-xs text-[var(--text-muted)]">请先添加来源引用</span>}</div></div></>}
            <div className="mt-4 flex justify-end gap-2"><button type="button" onClick={resetContentDraft} className="ios-btn-secondary rounded-md px-3 py-2 text-sm">取消</button><button type="button" onClick={() => void saveContent()} disabled={saving} className="ios-btn-primary flex items-center gap-1 rounded-md px-3 py-2 text-sm">{saving && <Loader2 className="h-4 w-4 animate-spin" />}保存条目</button></div>
          </section>}
        </main>
      </div>
    </div>
  </div>;
};

const Field: React.FC<{ label: string; value: unknown; onChange: (value: string) => void; type?: string }> = ({ label, value, onChange, type = 'text' }) => <label className="block text-xs font-semibold">{label}<input type={type} value={String(value ?? '')} onChange={event => onChange(event.target.value)} className="ios-input mt-1 w-full rounded-md px-2.5 py-2 text-sm" /></label>;
const TextAreaField: React.FC<{ label: string; value: unknown; onChange: (value: string) => void; full?: boolean }> = ({ label, value, onChange, full }) => <label className={`block text-xs font-semibold ${full ? 'md:col-span-2' : ''}`}>{label}<textarea value={String(value ?? '')} onChange={event => onChange(event.target.value)} className="ios-input mt-1 min-h-24 w-full rounded-md px-2.5 py-2 text-sm" /></label>;

export default KnowledgeBaseEditorModal;

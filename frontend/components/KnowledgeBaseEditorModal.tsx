import React, { useEffect, useMemo, useState } from 'react';
import { Bot, FileText, Loader2, Save, Send, Trash2, Upload, X } from 'lucide-react';
import {
  KnowledgeBaseDetail,
  KnowledgeFact,
  KnowledgeQAEntry,
  KnowledgeRule,
  KnowledgeSource,
  KnowledgeDocument,
  KnowledgeEvidence,
} from '../types';
import {
  askKnowledgeBase,
  createKnowledgeContent,
  deleteKnowledgeContent,
  deleteKnowledgeDocument,
  getKnowledgeDocument,
  getKnowledgeBase,
  importKnowledgeDocumentSections,
  uploadKnowledgeDocument,
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
const knowledgeErrorCode = (error: any) => error?.response?.data?.detail?.error_code as string | undefined;
const knowledgeErrorMessage = (error: any, fallback: string) => error?.response?.data?.detail?.message || getApiErrorMessage(error, fallback);
const itemCount = (value: unknown) => Array.isArray(value) ? value.length : 0;
const stringItems = (value: unknown) => Array.isArray(value) ? value.map(item => String(item).trim()) : [];
const validateDraft = (kind: Kind, draft: Draft | null): string | null => {
  if (!draft) return '请先创建或选择条目。';
  const priority = Number(draft.priority ?? 0);
  if (!Number.isInteger(priority) || priority < -100 || priority > 100) return '优先级必须是 -100 到 100 的整数。';
  if (itemCount(draft.source_ids) > 8) return '来源引用最多选择 8 条。';
  if (kind === 'facts') {
    const content = String(draft.content || '').trim();
    if (!content) return '请填写买家可见内容。';
    if (content.length > 800) return '买家可见内容不能超过 800 个字符。';
    if (String(draft.title || '').trim().length > 120) return '标题不能超过 120 个字符。';
    if (String(draft.category || '').trim().length > 80) return '分类不能超过 80 个字符。';
  }
  if (kind === 'sources') {
    const title = String(draft.title || '').trim();
    if (!title) return '请填写来源标题。';
    if (title.length > 120) return '来源标题不能超过 120 个字符。';
    if (String(draft.reference || '').trim().length > 500 || String(draft.notes || '').trim().length > 500) return '引用说明和备注均不能超过 500 个字符。';
    const url = String(draft.url || '').trim();
    if (url.length > 2000) return '来源 URL 不能超过 2000 个字符。';
    if (url && !/^https?:\/\/\S+$/i.test(url)) return '来源 URL 必须以 http:// 或 https:// 开头。';
  }
  if (kind === 'qa-entries') {
    const answer = String(draft.answer || '').trim();
    if (!answer) return '请填写公开答案。';
    if (answer.length > 800) return '公开答案不能超过 800 个字符。';
    if (String(draft.category || '').trim().length > 80) return '分类不能超过 80 个字符。';
    if (itemCount(draft.questions) > 20) return '问题最多填写 20 条。';
    if (itemCount(draft.keywords) > 30) return '关键词最多填写 30 条。';
    if (stringItems(draft.questions).some(value => !value || value.length > 80)) return '每条问题必须为 1 到 80 个字符。';
    if (stringItems(draft.keywords).some(value => !value || value.length > 32)) return '每个关键词必须为 1 到 32 个字符。';
  }
  if (kind === 'rules') {
    if (!String(draft.name || '').trim()) return '请填写规则名称。';
    if (String(draft.name || '').trim().length > 120) return '规则名称不能超过 120 个字符。';
    if (String(draft.intent || '').trim().length > 80) return '规则意图不能超过 80 个字符。';
    if (itemCount(draft.matchers) > 100) return '匹配词最多填写 100 条。';
    if (stringItems(draft.matchers).some(value => !value || value.length > 120)) return '每个匹配词必须为 1 到 120 个字符。';
    const ruleType = String(draft.rule_type || '');
    if (['fixed_reply', 'topic_refusal'].includes(ruleType) && (!itemCount(draft.matchers) || !String(draft.response || '').trim())) return '固定回复规则需要匹配词和回复内容。';
    if (['fixed_reply', 'topic_refusal'].includes(ruleType) && String(draft.response || '').trim().length > 300) return '固定回复内容不能超过 300 个字符。';
    if (ruleType === 'model_instruction' && !String(draft.instruction || '').trim()) return '请填写模型补充说明。';
    if (ruleType === 'model_instruction' && String(draft.instruction || '').trim().length > 800) return '模型补充说明不能超过 800 个字符。';
  }
  return null;
};

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
  const [answerEvidence, setAnswerEvidence] = useState<KnowledgeEvidence[]>([]);
  const [activeDocument, setActiveDocument] = useState<KnowledgeDocument | null>(null);
  const [selectedSections, setSelectedSections] = useState<string[]>([]);
  const [documentBusy, setDocumentBusy] = useState(false);

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
    const validationError = validateDraft(tab, draft);
    if (validationError) {
      notify(validationError, 'warning');
      return;
    }
    setSaving(true);
    try {
      const payload = contentPayload();
      delete payload.fact_key;
      delete payload.source_key;
      delete payload.rule_key;
      delete payload.qa_key;
      if (editingId) await updateKnowledgeContent(base.id, tab, editingId, base.version, payload);
      else await createKnowledgeContent(base.id, tab, base.version, payload);
      await reload(true);
      resetContentDraft();
      onSaved?.();
      notify('知识库内容已保存', 'success');
    } catch (error: any) {
      const code = knowledgeErrorCode(error);
      notify(code === 'knowledge_version_conflict' ? '版本已变化，请重新加载' : knowledgeErrorMessage(error, '保存内容失败'), 'error');
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
      setAnswerEvidence(result.provided_evidence || []);
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
      const code = knowledgeErrorCode(error);
      const message = code === 'knowledge_source_in_use'
        ? '该来源仍被知识条目引用，请先解除关联后再删除'
        : code === 'knowledge_version_conflict'
          ? '版本已变化，请重新加载'
          : knowledgeErrorMessage(error, '删除失败');
      notify(message, 'error');
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

  const openDocument = async (documentId: string) => {
    if (!base || documentBusy) return;
    setDocumentBusy(true);
    try {
      setActiveDocument(await getKnowledgeDocument(base.id, documentId));
      setSelectedSections([]);
    } catch (error) {
      notify(getApiErrorMessage(error, '文档详情加载失败'), 'error');
    } finally {
      setDocumentBusy(false);
    }
  };

  const uploadDocument = async (file: File | undefined) => {
    if (!base || !file || documentBusy) return;
    if (!/\.(md|markdown|txt)$/i.test(file.name)) {
      notify('仅支持 Markdown（.md/.markdown）和 TXT 文档', 'warning');
      return;
    }
    if (file.size > 512 * 1024) {
      notify('文档不能超过 512 KiB', 'warning');
      return;
    }
    setDocumentBusy(true);
    try {
      const result = await uploadKnowledgeDocument(base.id, base.version, file);
      await reload(true);
      setActiveDocument(result.document);
      setSelectedSections([]);
      notify(result.duplicate ? '该文档已存在，已打开原文档' : '文档已上传；选择章节并导入后才会进入 AI', result.duplicate ? 'info' : 'success');
    } catch (error) {
      notify(getApiErrorMessage(error, '文档上传失败'), 'error');
    } finally {
      setDocumentBusy(false);
    }
  };

  const importSelectedSections = async () => {
    if (!base || !activeDocument || !selectedSections.length || documentBusy) return;
    const ok = await confirmAction(
      `将 ${selectedSections.length} 个章节导入为买家可见事实，并允许 AI 在匹配时使用，继续吗？`,
      { title: '确认导入知识', confirmLabel: '导入所选章节', danger: false },
    );
    if (!ok) return;
    setDocumentBusy(true);
    try {
      await importKnowledgeDocumentSections(base.id, activeDocument.id, base.version, selectedSections);
      const updated = await reload(true);
      setActiveDocument(await getKnowledgeDocument(updated.id, activeDocument.id));
      setSelectedSections([]);
      notify('所选章节已导入并关联来源', 'success');
      onSaved?.();
    } catch (error) {
      notify(getApiErrorMessage(error, '章节导入失败'), 'error');
    } finally {
      setDocumentBusy(false);
    }
  };

  const removeDocument = async (document: KnowledgeDocument) => {
    if (!base || documentBusy) return;
    const deleteImported = document.linked_entry_count > 0;
    const ok = await confirmAction(
      deleteImported
        ? `该文档关联 ${document.linked_entry_count} 个条目。仅当这些条目均由文档自动导入时，才会一并删除。`
        : `确认删除文档“${document.original_filename}”吗？`,
      { title: '删除知识文档', confirmLabel: deleteImported ? '删除文档和自动导入条目' : '删除文档', danger: true },
    );
    if (!ok) return;
    setDocumentBusy(true);
    try {
      await deleteKnowledgeDocument(base.id, document.id, base.version, deleteImported);
      await reload(true);
      if (activeDocument?.id === document.id) setActiveDocument(null);
      notify('文档已删除', 'success');
      onSaved?.();
    } catch (error) {
      const code = knowledgeErrorCode(error);
      notify(code === 'knowledge_document_in_use'
        ? '该文档仍有关联条目；请选择连同自动导入条目删除，或先解除手工关联'
        : knowledgeErrorMessage(error, '文档删除失败'), 'error');
    } finally {
      setDocumentBusy(false);
    }
  };

  if (loading) return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"><div className="rounded-xl bg-[var(--surface)] p-6"><Loader2 className="h-5 w-5 animate-spin" /></div></div>;
  if (!base) return null;

  const ruleType = String(draft?.rule_type || 'model_instruction');
  const draftValidationError = draft ? validateDraft(tab, draft) : null;
  const draftValid = Boolean(draft && !draftValidationError);

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
            {answer && <div className="mt-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3" role="status"><div className="flex items-center justify-between gap-3"><span className="text-xs font-semibold text-[var(--text-muted)]">AI 回答</span>{answerModel && <span className="text-xs text-[var(--text-soft)]">{answerModel}</span>}</div><p className="mt-2 whitespace-pre-wrap text-sm leading-6">{answer}</p><div className="mt-3 border-t border-[var(--border)] pt-2"><p className="text-xs font-semibold">本次提供给 AI 的依据</p>{answerEvidence.length ? <ul className="mt-1 space-y-1 text-xs text-[var(--text-muted)]">{answerEvidence.map((item, index) => <li key={`${item.content_key}-${index}`}>{item.source_title} · {item.content_type === 'fact' ? '事实' : '问答'} · {item.document_status === 'metadata_only' ? '仅引用记录，未上传文件' : item.document_status === 'parsed' ? '文档已上传但未导入' : item.document_status === 'partially_imported' ? '文档部分导入' : '文档已导入'}</li>)}</ul> : <p className="mt-1 text-xs text-[var(--text-muted)]">未提供关联来源</p>}</div></div>}
          </section>
          <section className="mb-5 rounded-xl border border-[var(--border)] p-4" aria-labelledby="knowledge-documents-title">
            <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 id="knowledge-documents-title" className="flex items-center gap-2 font-bold"><FileText className="h-4 w-4" />知识文档</h3><p className="mt-1 text-xs text-[var(--text-muted)]">上传后先预览；只有明确导入的章节才会成为买家可见事实并进入 AI。</p></div><label className="ios-btn-primary flex cursor-pointer items-center gap-1 rounded-md px-3 py-2 text-sm"><Upload className="h-4 w-4" />{documentBusy ? '处理中' : '上传文档'}<input type="file" className="sr-only" accept=".md,.markdown,.txt,text/markdown,text/plain" disabled={documentBusy} onChange={event => { void uploadDocument(event.target.files?.[0]); event.currentTarget.value = ''; }} /></label></div>
            <div className="mt-3 grid gap-2 md:grid-cols-2">{(base.documents || []).map(document => <div key={document.id} className="flex items-center gap-2 rounded-lg border border-[var(--border)] p-3"><button type="button" onClick={() => void openDocument(document.id)} disabled={documentBusy} className="min-w-0 flex-1 text-left"><p className="truncate text-sm font-semibold">{document.original_filename}</p><p className="mt-1 text-xs text-[var(--text-muted)]">{document.status === 'parsed' ? '已上传，尚未进入 AI' : document.status === 'partially_imported' ? '部分章节已导入' : '全部章节已导入'} · {document.imported_section_count}/{document.section_count} 章节</p></button><button type="button" onClick={() => void removeDocument(document)} disabled={documentBusy} className="rounded p-1.5 text-red-600" aria-label={`删除文档 ${document.original_filename}`}><Trash2 className="h-4 w-4" /></button></div>)}{!(base.documents || []).length && <p className="md:col-span-2 rounded-lg border border-dashed border-[var(--border)] px-3 py-6 text-center text-sm text-[var(--text-muted)]">尚未上传文档。来源引用中的文件名只是一条引用记录，不能证明文件已上传。</p>}</div>
            {activeDocument?.sections && <div className="mt-4 rounded-lg bg-[var(--surface-hover)] p-3"><div className="flex items-center justify-between gap-2"><div><p className="text-sm font-bold">预览：{activeDocument.original_filename}</p><p className="text-xs text-[var(--text-muted)]">勾选要公开给买家并提供给 AI 的章节。</p></div><button type="button" onClick={() => void importSelectedSections()} disabled={documentBusy || !selectedSections.length} className="ios-btn-primary rounded-md px-3 py-2 text-sm">导入所选章节</button></div><div className="mt-3 space-y-2">{activeDocument.sections.map(section => <label key={section.id} className="block rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3 text-sm"><span className="flex items-center gap-2 font-semibold"><input type="checkbox" disabled={section.imported} checked={section.imported || selectedSections.includes(section.id)} onChange={() => setSelectedSections(current => current.includes(section.id) ? current.filter(id => id !== section.id) : [...current, section.id])} />{section.heading_path}{section.imported ? '（已导入）' : ''}</span><span className="mt-2 block whitespace-pre-wrap text-xs leading-5 text-[var(--text-muted)]">{section.content}</span></label>)}</div></div>}
          </section>
          <div className="mb-4 flex items-center justify-between gap-3"><div><h3 className="font-bold">{tabs.find(item => item.kind === tab)?.label}</h3><p className="text-xs text-[var(--text-muted)]">可单独保存、停用或删除条目；保存时使用版本校验。</p></div><button type="button" onClick={() => void startAdd()} disabled={saving} className="ios-btn-primary rounded-md px-3 py-2 text-sm">新增条目</button></div>
          <div className="space-y-2">{contents.map(entry => <div key={entry.id} className="rounded-xl border border-[var(--border)] p-3"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="font-semibold">{('name' in entry && entry.name) || ('title' in entry && entry.title) || ('rule_key' in entry && entry.rule_key) || ('qa_key' in entry && entry.qa_key)}</p><p className="mt-1 line-clamp-2 text-sm text-[var(--text-muted)]">{('content' in entry && entry.content) || ('answer' in entry && entry.answer) || ('reference' in entry && entry.reference) || ('instruction' in entry && entry.instruction) || '暂无内容'}</p>{tab === 'sources' && <div className="mt-2 text-xs text-brand-ink"><p className="font-medium">{(entry as KnowledgeSource).document_status === 'metadata_only' ? '仅引用记录 · 未上传文件' : (entry as KnowledgeSource).document_status === 'parsed' ? '已上传 · 尚未导入' : (entry as KnowledgeSource).document_status === 'partially_imported' ? '已上传 · 部分导入' : '已上传 · 已导入'} · 关联 {(entry as KnowledgeSource).linked_entry_count || 0} 条 · AI 可用 {(entry as KnowledgeSource).runtime_enabled_count || 0} 条</p>{Boolean((entry as KnowledgeSource).usage?.length) && <details className="mt-1"><summary className="cursor-pointer">查看关联条目</summary><ul className="mt-1 list-disc space-y-1 pl-4 text-[var(--text-muted)]">{(entry as KnowledgeSource).usage?.map(item => <li key={item.content_id}>{item.kind === 'fact' ? '事实' : item.kind === 'qa' ? '问答' : '规则'}：{item.label}{item.enabled ? '' : '（已停用）'}</li>)}</ul></details>}</div>}</div>{tab === 'sources' && (entry as KnowledgeSource).source_kind === 'document' ? <span className="shrink-0 text-xs text-[var(--text-muted)]">由文档管理</span> : <div className="flex shrink-0 gap-2"><button type="button" disabled={saving} onClick={() => void startEdit(entry)} className="ios-btn-secondary rounded-md px-2 py-1 text-xs">编辑</button><button type="button" disabled={saving} onClick={() => void removeContent(entry)} className="rounded-md px-2 py-1 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50">删除</button></div>}</div></div>)}{!contents.length && <p className="rounded-xl border border-dashed border-[var(--border)] px-4 py-10 text-center text-sm text-[var(--text-muted)]">暂无条目，点击“新增条目”开始维护。</p>}</div>

          {draft && <section className="mt-5 rounded-xl border border-brand-200 bg-brand-50/40 p-4">
            <div className="grid gap-3 md:grid-cols-2">
              {tab === 'facts' && <>{editingId && <ReadOnlyKey value={draft.fact_key} />}<Field label="分类" value={draft.category} onChange={value => change('category', value)} /><Field label="标题" value={draft.title} onChange={value => change('title', value)} /><Field label="优先级" type="number" value={draft.priority} onChange={value => change('priority', Number(value))} /><TextAreaField label="买家可见内容（必填）" value={draft.content} onChange={value => change('content', value)} full /></>}
              {tab === 'sources' && <>{editingId && <ReadOnlyKey value={draft.source_key} />}<Field label="标题（必填）" value={draft.title} onChange={value => change('title', value)} /><Field label="引用说明" value={draft.reference} onChange={value => change('reference', value)} /><Field label="URL（可选）" value={draft.url} onChange={value => change('url', value)} /><TextAreaField label="备注（不会提供给 AI）" value={draft.notes} onChange={value => change('notes', value)} full /></>}
              {tab === 'rules' && <>{editingId && <ReadOnlyKey value={draft.rule_key} />}<Field label="规则名称" value={draft.name} onChange={value => change('name', value)} /><label className="block text-xs font-semibold">规则类型<select value={ruleType} onChange={event => changeRuleType(event.target.value)} className="ios-input mt-1 w-full rounded-md px-2.5 py-2 text-sm">{ruleTypes.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><Field label="意图" value={draft.intent} onChange={value => change('intent', value)} /><TextAreaField label="匹配词（每行一个）" value={asLines(draft.matchers)} onChange={value => change('matchers', value.split('\n').map(item => item.trim()).filter(Boolean))} />{ruleType === 'model_instruction' && <TextAreaField label="内部指令" value={draft.instruction} onChange={value => change('instruction', value)} full />}{['fixed_reply', 'topic_refusal'].includes(ruleType) && <TextAreaField label="固定回复" value={draft.response} onChange={value => change('response', value)} full />}{ruleType === 'pricing_policy' && <><Field label="原价" value={configField(draft.config_json, 'original_price')} onChange={value => changeConfig('original_price', value)} /><Field label="当前价" value={configField(draft.config_json, 'current_price')} onChange={value => changeConfig('current_price', value)} /><Field label="活动说明" value={configField(draft.config_json, 'promotion_label')} onChange={value => changeConfig('promotion_label', value)} /><Field label="活动结束时间（可选）" value={configField(draft.config_json, 'promotion_end')} onChange={value => changeConfig('promotion_end', value || null)} /></>}{ruleType === 'bargain_policy' && <><Field label="最大优惠比例" type="number" value={configField(draft.config_json, 'max_discount_percent')} onChange={value => changeConfig('max_discount_percent', Number(value))} /><Field label="最大优惠金额" value={configField(draft.config_json, 'max_discount_amount')} onChange={value => changeConfig('max_discount_amount', value)} /><Field label="最大议价轮数" type="number" value={configField(draft.config_json, 'max_rounds')} onChange={value => changeConfig('max_rounds', Number(value))} /><label className="block text-xs font-semibold">底价方式<select value={String(configField(draft.config_json, 'floor_mode') || 'current_price')} onChange={event => changeConfig('floor_mode', event.target.value)} className="ios-input mt-1 w-full rounded-md px-2.5 py-2 text-sm"><option value="current_price">当前商品价格</option><option value="fixed">固定底价</option></select></label>{configField(draft.config_json, 'floor_mode') === 'fixed' && <Field label="固定底价" value={configField(draft.config_json, 'floor_price')} onChange={value => changeConfig('floor_price', value)} />}</>}{ruleType === 'output_guard' && <><TextAreaField label="未被询问时禁止输出（每行一个）" value={asLines(configField(draft.config_json, 'forbidden_unless_asked'))} onChange={value => changeConfig('forbidden_unless_asked', value.split('\n').map(item => item.trim()).filter(Boolean))} full /><label className="block text-xs font-semibold">拦截后的回复<select value={String(configField(draft.config_json, 'fallback_mode') || 'human_confirmation')} onChange={event => changeConfig('fallback_mode', event.target.value)} className="ios-input mt-1 w-full rounded-md px-2.5 py-2 text-sm"><option value="human_confirmation">转人工确认</option><option value="top_match">使用最佳知识答案</option></select></label></>}</>}
              {tab === 'qa-entries' && <>{editingId ? <div className="text-xs"><p className="font-semibold">内部标识</p><p className="mt-1 rounded-md bg-[var(--surface-hover)] px-2.5 py-2 font-mono">{String(draft.qa_key || '')}</p></div> : <div className="text-xs"><p className="font-semibold">内部标识</p><p className="mt-1 rounded-md bg-[var(--surface-hover)] px-2.5 py-2 text-[var(--text-muted)]">留空后由系统自动生成</p></div>}<Field label="分类" value={draft.category} onChange={value => change('category', value)} /><TextAreaField label="问题（每行一个）" value={asLines(draft.questions)} onChange={value => change('questions', value.split('\n').map(item => item.trim()).filter(Boolean))} /><TextAreaField label="关键词（每行一个）" value={asLines(draft.keywords)} onChange={value => change('keywords', value.split('\n').map(item => item.trim()).filter(Boolean))} /><TextAreaField label="公开答案" value={draft.answer} onChange={value => change('answer', value)} full /></>}
            </div>
            {tab !== 'sources' && <><label className="mt-3 inline-flex items-center gap-2 text-xs font-semibold"><input type="checkbox" checked={draft.enabled !== false} onChange={event => change('enabled', event.target.checked)} />启用此条目</label><div className="mt-3"><p className="mb-1 text-xs font-semibold">来源引用（可选）</p><div className="flex flex-wrap gap-2">{base.sources.map(source => <label key={source.id} className="flex items-center gap-1 text-xs"><input type="checkbox" checked={sourceIds.includes(source.id)} onChange={() => toggleSource(source.id)} />{source.title}</label>)}{!base.sources.length && <span className="text-xs text-[var(--text-muted)]">请先添加来源引用</span>}</div></div></>}
            {draftValidationError && <p className="mt-3 text-xs text-red-600" role="alert">{draftValidationError}</p>}
            <div className="mt-4 flex justify-end gap-2"><button type="button" onClick={resetContentDraft} className="ios-btn-secondary rounded-md px-3 py-2 text-sm">取消</button><button type="button" onClick={() => void saveContent()} disabled={saving || !draftValid || !contentDirty} className="ios-btn-primary flex items-center gap-1 rounded-md px-3 py-2 text-sm">{saving && <Loader2 className="h-4 w-4 animate-spin" />}保存条目</button></div>
          </section>}
        </main>
      </div>
    </div>
  </div>;
};

const ReadOnlyKey: React.FC<{ value: unknown }> = ({ value }) => <div className="text-xs"><p className="font-semibold">内部标识</p><p className="mt-1 rounded-md bg-[var(--surface-hover)] px-2.5 py-2 text-[var(--text-muted)]">{String(value || '由系统自动生成')}</p></div>;
const Field: React.FC<{ label: string; value: unknown; onChange: (value: string) => void; type?: string }> = ({ label, value, onChange, type = 'text' }) => ['事实键', '来源键', '规则键'].includes(label) ? <ReadOnlyKey value={value} /> : <label className="block text-xs font-semibold">{label}<input type={type} value={String(value ?? '')} onChange={event => onChange(event.target.value)} className="ios-input mt-1 w-full rounded-md px-2.5 py-2 text-sm" /></label>;
const TextAreaField: React.FC<{ label: string; value: unknown; onChange: (value: string) => void; full?: boolean }> = ({ label, value, onChange, full }) => <label className={`block text-xs font-semibold ${full ? 'md:col-span-2' : ''}`}>{label}<textarea value={String(value ?? '')} onChange={event => onChange(event.target.value)} className="ios-input mt-1 min-h-24 w-full rounded-md px-2.5 py-2 text-sm" /></label>;

export default KnowledgeBaseEditorModal;

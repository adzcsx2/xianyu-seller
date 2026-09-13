import React, { useEffect, useMemo, useRef, useState } from 'react';
import { BookOpen, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { AccountDetail, Item, KnowledgeBaseSummary, KnowledgeBinding } from '../types';
import {
  addKnowledgeBinding,
  createKnowledgeBase,
  deleteKnowledgeBase,
  getAccountDetails,
  getItems,
  getKnowledgeBindings,
  listKnowledgeBases,
  removeKnowledgeBinding,
} from '../services/api';
import { confirmAction, notify } from '../services/feedback';
import { useFeatureFlags } from '../contexts/FeatureFlagsContext';
import { PageHeader, PageLoading } from './ui';
import KnowledgeBaseEditorModal from './KnowledgeBaseEditorModal';

const KnowledgeBase: React.FC = () => {
  const { isEnabled } = useFeatureFlags();
  const knowledgeBaseEnabled = isEnabled('feature_knowledge_base_enabled');
  const [accounts, setAccounts] = useState<AccountDetail[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [bases, setBases] = useState<KnowledgeBaseSummary[]>([]);
  const [bindings, setBindings] = useState<KnowledgeBinding[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [selectedItemId, setSelectedItemId] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [bindingModal, setBindingModal] = useState<'add' | 'remove' | null>(null);
  const [creating, setCreating] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createDescription, setCreateDescription] = useState('');
  const [editingBaseId, setEditingBaseId] = useState<string | null>(null);
  const [knowledgeDirty, setKnowledgeDirty] = useState(false);
  const [operationKey, setOperationKey] = useState<string | null>(null);
  const bindingRequestRef = useRef(0);
  const mountedRef = useRef(true);

  const accountItems = useMemo(
    () => items.filter(item => item.cookie_id === selectedAccountId),
    [items, selectedAccountId],
  );
  const boundIds = useMemo(
    () => new Set(bindings.map(binding => binding.knowledge_base_id)),
    [bindings],
  );
  const selectedItem = useMemo(
    () => accountItems.find(item => item.item_id === selectedItemId),
    [accountItems, selectedItemId],
  );
  const currentProjectKnowledgeTitle = selectedItem?.item_title || selectedItemId;
  const availableBaseCount = useMemo(
    () => bases.filter(base => !boundIds.has(base.id)).length,
    [bases, boundIds],
  );

  const loadBases = async () => setBases(await listKnowledgeBases());
  const loadBindings = async (cookieId = selectedAccountId, itemId = selectedItemId) => {
    const requestId = ++bindingRequestRef.current;
    if (!cookieId || !itemId) {
      if (mountedRef.current && requestId === bindingRequestRef.current) setBindings([]);
      return;
    }
    const result = await getKnowledgeBindings(cookieId, itemId);
    if (mountedRef.current && requestId === bindingRequestRef.current) setBindings(result);
  };
  const reload = async () => {
    setRefreshing(true);
    try {
      await Promise.all([loadBases(), loadBindings()]);
    } catch (error) {
      notify(error instanceof Error ? error.message : '知识库加载失败', 'error');
    } finally {
      setRefreshing(false);
    }
  };

  const confirmDiscardChanges = async () => !knowledgeDirty || confirmAction(
    '当前知识库内容尚未保存，确定放弃修改并切换吗？',
    { title: '放弃未保存内容', confirmLabel: '放弃并切换', danger: true },
  );
  const closeEditorAfterDiscard = () => {
    setKnowledgeDirty(false);
    setEditingBaseId(null);
  };
  const handleAccountChange = async (accountId: string) => {
    if (!(await confirmDiscardChanges())) return;
    closeEditorAfterDiscard();
    bindingRequestRef.current += 1;
    setSelectedAccountId(accountId);
    setSelectedItemId(items.find(item => item.cookie_id === accountId)?.item_id || '');
  };
  const handleItemChange = async (itemId: string) => {
    if (!(await confirmDiscardChanges())) return;
    closeEditorAfterDiscard();
    bindingRequestRef.current += 1;
    setSelectedItemId(itemId);
  };
  const handleReload = async () => {
    if (!(await confirmDiscardChanges())) return;
    closeEditorAfterDiscard();
    await reload();
  };
  const openCreateDialog = () => {
    setBindingModal(null);
    setCreating(true);
  };

  useEffect(() => {
    Promise.all([getAccountDetails(), getItems(), listKnowledgeBases()])
      .then(([accountData, itemData, baseData]) => {
        if (!mountedRef.current) return;
        setAccounts(accountData);
        setItems(itemData);
        setBases(baseData);
        const accountId = accountData[0]?.id || '';
        setSelectedAccountId(accountId);
        setSelectedItemId(itemData.find(item => item.cookie_id === accountId)?.item_id || '');
      })
      .catch(error => {
        if (mountedRef.current) notify(error instanceof Error ? error.message : '知识库页面加载失败', 'error');
      })
      .finally(() => {
        if (mountedRef.current) setLoading(false);
      });
  }, []);

  useEffect(() => () => {
    mountedRef.current = false;
    bindingRequestRef.current += 1;
  }, []);

  useEffect(() => {
    void loadBindings();
    // Binding scope is fully identified by these two values.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAccountId, selectedItemId]);

  const handleAddBinding = async (base: KnowledgeBaseSummary) => {
    if (!knowledgeBaseEnabled) return;
    if (operationKey || boundIds.has(base.id) || !selectedAccountId || !selectedItemId) return;
    setOperationKey(`bind-add:${base.id}`);
    try {
      await addKnowledgeBinding(selectedAccountId, selectedItemId, base.id);
      await Promise.all([loadBindings(), loadBases()]);
      setBindingModal(null);
      notify('知识库已添加到当前商品', 'success');
    } catch (error: any) {
      if (error?.response?.status === 409) await Promise.all([loadBindings(), loadBases()]);
      notify(error?.response?.status === 409 ? '该知识库已添加，请刷新后重试' : '添加知识库失败', 'error');
    } finally {
      setOperationKey(null);
    }
  };

  const handleRemoveBinding = async (binding: KnowledgeBinding) => {
    if (!knowledgeBaseEnabled) return;
    const ok = await confirmAction(
      `确认仅从当前商品移除“${binding.name}”吗？不会删除全部知识库中的内容。`,
      { title: '删除当前商品知识库', confirmLabel: '移除绑定', danger: true },
    );
    if (!ok || operationKey) return;
    setOperationKey(`bind-remove:${binding.knowledge_base_id}`);
    try {
      await removeKnowledgeBinding(selectedAccountId, selectedItemId, binding.knowledge_base_id);
      await Promise.all([loadBindings(), loadBases()]);
      setBindingModal(null);
      notify('已从当前商品移除知识库', 'success');
    } catch (error) {
      notify(error instanceof Error ? error.message : '移除绑定失败', 'error');
    } finally {
      setOperationKey(null);
    }
  };

  const handleCreate = async () => {
    if (!knowledgeBaseEnabled) return;
    if (!createName.trim() || operationKey) return;
    setOperationKey('create-base');
    try {
      const base = await createKnowledgeBase(createName.trim(), createDescription.trim());
      await loadBases();
      setCreating(false);
      setCreateName('');
      setCreateDescription('');
      setEditingBaseId(base.id);
      notify('知识库已创建', 'success');
    } catch (error) {
      notify(error instanceof Error ? error.message : '创建知识库失败', 'error');
    } finally {
      setOperationKey(null);
    }
  };

  const handleDeleteBase = async (base: KnowledgeBaseSummary) => {
    if (!knowledgeBaseEnabled) return;
    const ok = await confirmAction(
      `“${base.name}”将被全局删除，同时删除其中的事实、来源、规则、问答和 ${base.binding_count} 个商品绑定。此操作不可撤销，继续吗？`,
      { title: '删除全部知识库', confirmLabel: '确定删除', danger: true },
    );
    if (!ok || operationKey) return;
    setOperationKey(`delete-base:${base.id}`);
    try {
      await deleteKnowledgeBase(base.id, base.version);
      if (editingBaseId === base.id) closeEditorAfterDiscard();
      await Promise.all([loadBases(), loadBindings()]);
      notify('知识库已全局删除', 'success');
    } catch (error: any) {
      notify(error?.response?.status === 409 ? '版本已变化，请刷新后重试' : '删除知识库失败', 'error');
    } finally {
      setOperationKey(null);
    }
  };

  useEffect(() => {
    if (!bindingModal && !creating) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || operationKey) return;
      setBindingModal(null);
      setCreating(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [bindingModal, creating, operationKey]);

  if (loading) return <PageLoading label="正在加载知识库" />;

  return <div className="page-stack animate-fade-in">
    <PageHeader
      title="知识库"
      description="全局知识库可复用于多个商品；商品只保存绑定关系。"
      icon={BookOpen}
      actions={<button type="button" onClick={() => void handleReload()} disabled={refreshing} className="ios-btn-secondary flex items-center gap-2 rounded-md px-3 py-2 text-sm"><RefreshCw className={refreshing ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />重新加载</button>}
    />

    <section className="section-panel grid gap-4 p-4 md:grid-cols-2">
      <label><span className="field-label">账号</span><select value={selectedAccountId} onChange={event => void handleAccountChange(event.target.value)} disabled={!accounts.length || operationKey !== null} className="ios-input w-full rounded-md px-3 py-2 text-sm"><option value="">{accounts.length ? '请选择账号' : '暂无账号'}</option>{accounts.map(account => <option key={account.id} value={account.id}>{account.nickname || account.remark || account.id}</option>)}</select></label>
      <label><span className="field-label">商品</span><select value={selectedItemId} onChange={event => void handleItemChange(event.target.value)} disabled={!accountItems.length || operationKey !== null} className="ios-input w-full rounded-md px-3 py-2 text-sm"><option value="">{accountItems.length ? '请选择商品' : '暂无商品'}</option>{accountItems.map(item => <option key={item.item_id} value={item.item_id}>{item.item_title || item.item_id} · {item.item_price || '未定价'}</option>)}</select></label>
    </section>

    <section className="section-panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-lg font-bold" title={currentProjectKnowledgeTitle || undefined}>
            {currentProjectKnowledgeTitle ? `${currentProjectKnowledgeTitle} · 当前项目知识库` : '当前项目知识库'}
          </h2>
          <p className="mt-1 text-sm text-[var(--text-muted)]">仅显示当前商品真实绑定的知识库</p>
        </div>
        <div className="flex gap-2"><button type="button" onClick={() => setBindingModal('add')} disabled={!selectedItemId} className="ios-btn-secondary flex items-center gap-2 rounded-md px-3 py-2 text-sm"><Plus className="h-4 w-4" />添加知识库</button><button type="button" onClick={() => setBindingModal('remove')} disabled={!bindings.length} className="ios-btn-secondary rounded-md px-3 py-2 text-sm">删除知识库</button></div>
      </div>
      <div className="mt-4 space-y-2">
        {bindings.map(binding => <div key={binding.knowledge_base_id} className="flex items-center justify-between rounded-xl border border-[var(--border)] px-4 py-3"><div><p className="font-semibold">{binding.name}</p><p className="text-xs text-[var(--text-muted)]">{binding.description || '暂无描述'}</p></div><span className="text-xs text-[var(--text-muted)]">已绑定</span></div>)}
        {!bindings.length && <p className="rounded-xl border border-dashed border-[var(--border)] px-4 py-8 text-center text-sm text-[var(--text-muted)]">{selectedItemId ? '当前商品暂未添加知识库' : '请先选择商品'}</p>}
      </div>
    </section>

    <section className="section-panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-bold">全部知识库</h2><p className="mt-1 text-sm text-[var(--text-muted)]">点击列表项编辑四类内容：买家可见事实、来源引用、内部规则、公开问答条目</p></div><button type="button" onClick={openCreateDialog} disabled={operationKey !== null} className="ios-btn-primary flex items-center gap-2 rounded-md px-3 py-2 text-sm"><Plus className="h-4 w-4" />添加知识库</button></div>
      <div className="mt-4 space-y-2">
        {bases.map(base => <div key={base.id} className="flex items-center gap-2 rounded-xl border border-[var(--border)] hover:bg-[var(--surface-hover)]"><button type="button" onClick={() => setEditingBaseId(base.id)} disabled={operationKey !== null} className="min-w-0 flex-1 px-4 py-3 text-left" aria-label={`编辑知识库 ${base.name}`}><p className="font-semibold">{base.name}</p><p className="text-xs text-[var(--text-muted)]">{base.description || '暂无描述'} · 事实 {base.fact_count} · 来源 {base.source_count} · 规则 {base.rule_count} · 问答 {base.qa_count}</p></button><button type="button" onClick={() => void handleDeleteBase(base)} disabled={operationKey !== null} className="mr-2 rounded-md p-2 text-red-600 hover:bg-red-50 disabled:opacity-50" title="全局删除知识库" aria-label={`删除知识库 ${base.name}`}><Trash2 className="h-4 w-4" /></button></div>)}
        {!bases.length && <p className="rounded-xl border border-dashed border-[var(--border)] px-4 py-8 text-center text-sm text-[var(--text-muted)]">暂无知识库，请点击“添加知识库”创建</p>}
      </div>
    </section>

    {bindingModal && <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true" aria-labelledby="binding-dialog-title">
      <div className="w-full max-w-lg rounded-2xl bg-[var(--surface)] p-5 shadow-xl">
        <div className="flex items-center justify-between">
          <h2 id="binding-dialog-title" className="text-lg font-bold">{bindingModal === 'add' ? '添加到当前商品' : '删除知识库'}</h2>
          <button type="button" onClick={() => setBindingModal(null)} disabled={operationKey !== null} className="text-sm text-[var(--text-muted)] disabled:opacity-50">关闭</button>
        </div>
        {bindingModal === 'add' ? <div className="mt-4 space-y-3">
          <div className="rounded-xl bg-[var(--surface-hover)] px-4 py-3 text-sm text-[var(--text-muted)]">
            <p>当前商品：<span className="font-medium text-[var(--text)]">{selectedItem?.item_title || selectedItemId}</span></p>
            <p className="mt-1">可添加 {availableBaseCount} 个知识库；已经添加的知识库不能重复添加。</p>
          </div>
          {availableBaseCount === 0 && <p role="status" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">当前商品已经添加了全部知识库，不能重复添加。</p>}
          {bases.map(base => <button key={base.id} type="button" disabled={operationKey !== null || boundIds.has(base.id)} onClick={() => void handleAddBinding(base)} className="flex w-full items-center justify-between rounded-xl border border-[var(--border)] px-4 py-3 text-left disabled:cursor-not-allowed disabled:opacity-50"><span>{base.name}</span><span className="text-xs text-[var(--text-muted)]">{boundIds.has(base.id) ? '已添加到当前商品' : operationKey === `bind-add:${base.id}` ? '添加中' : '添加'}</span></button>)}
          {!bases.length && <p className="rounded-xl border border-dashed border-[var(--border)] px-4 py-8 text-center text-sm text-[var(--text-muted)]">暂无可添加的知识库</p>}
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border)] pt-3">
            <p className="text-xs text-[var(--text-muted)]">需要其他内容？新建完成后可返回这里添加。</p>
            <button type="button" onClick={openCreateDialog} disabled={operationKey !== null} className="ios-btn-secondary flex items-center gap-2 rounded-md px-3 py-2 text-sm"><Plus className="h-4 w-4" />新建知识库</button>
          </div>
        </div> : <div className="mt-4 space-y-2">{bindings.map(binding => <button key={binding.knowledge_base_id} type="button" disabled={operationKey !== null} onClick={() => void handleRemoveBinding(binding)} className="flex w-full items-center justify-between rounded-xl border border-[var(--border)] px-4 py-3 text-left disabled:opacity-50"><span>{binding.name}</span><span className="text-xs text-red-600">{operationKey === `bind-remove:${binding.knowledge_base_id}` ? '移除中' : '移除绑定'}</span></button>)}</div>}
      </div>
    </div>}

    {creating && <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true" aria-labelledby="create-knowledge-title"><div className="w-full max-w-lg rounded-2xl bg-[var(--surface)] p-5 shadow-xl"><h2 id="create-knowledge-title" className="text-lg font-bold">新建知识库</h2><input autoFocus value={createName} onChange={event => setCreateName(event.target.value)} disabled={operationKey !== null} className="ios-input mt-4 w-full rounded-md px-3 py-2 text-sm" placeholder="知识库名称" /><textarea value={createDescription} onChange={event => setCreateDescription(event.target.value)} disabled={operationKey !== null} className="ios-input mt-3 min-h-24 w-full rounded-md px-3 py-2 text-sm" placeholder="描述（可选）" /><div className="mt-4 flex justify-end gap-2"><button type="button" onClick={() => setCreating(false)} disabled={operationKey !== null} className="ios-btn-secondary rounded-md px-3 py-2 text-sm">取消</button><button type="button" onClick={() => void handleCreate()} disabled={operationKey !== null || !createName.trim()} className="ios-btn-primary rounded-md px-3 py-2 text-sm">{operationKey === 'create-base' ? '创建中' : '创建'}</button></div></div></div>}

    {editingBaseId && <KnowledgeBaseEditorModal baseId={editingBaseId} aiConfigAccountId={selectedAccountId} onClose={() => { setKnowledgeDirty(false); setEditingBaseId(null); }} onDirtyChange={setKnowledgeDirty} onSaved={() => { void reload(); }} />}
  </div>;
};

export default KnowledgeBase;

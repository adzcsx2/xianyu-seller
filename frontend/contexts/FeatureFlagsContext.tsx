import React, {
  createContext,
  PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { getApiErrorMessage } from '../services/feedback';
import { getFeatureFlags, updateFeatureFlags } from '../services/api';
import {
  FeatureFlagPatch,
  FeatureFlagSnapshot,
  FeatureFlagsUpdateResponse,
  FeatureKey,
  FeatureRuntimeApplyStatus,
} from '../types';

export interface FeatureFlagsContextValue {
  snapshot: FeatureFlagSnapshot | null;
  loading: boolean;
  updating: boolean;
  error: string | null;
  runtimeApply: FeatureRuntimeApplyStatus | null;
  isAdmin: boolean;
  load: () => Promise<void>;
  update: (flags: FeatureFlagPatch) => Promise<FeatureFlagsUpdateResponse>;
  isEnabled: (key: FeatureKey) => boolean;
}

const FeatureFlagsContext = createContext<FeatureFlagsContextValue | undefined>(undefined);

export const FeatureFlagsProvider: React.FC<PropsWithChildren<{ isAdmin: boolean }>> = ({
  isAdmin,
  children,
}) => {
  const [snapshot, setSnapshot] = useState<FeatureFlagSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runtimeApply, setRuntimeApply] = useState<FeatureRuntimeApplyStatus | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const next = await getFeatureFlags();
      setSnapshot(next);
      setRuntimeApply(null);
      setError(null);
    } catch (cause) {
      // 没有服务端事实源时保持 null，调用方的 isEnabled 必须 fail closed。
      setSnapshot(null);
      setError(getApiErrorMessage(cause, '功能开关加载失败'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const update = useCallback(async (flags: FeatureFlagPatch) => {
    if (!snapshot) throw new Error('功能开关尚未加载');
    setUpdating(true);
    try {
      const next = await updateFeatureFlags(snapshot.revision, flags);
      // 服务端返回 canonical snapshot；不在前端自行推导 effective 或 revision。
      setSnapshot(next);
      setRuntimeApply(next.runtime_apply);
      setError(null);
      return next;
    } catch (cause) {
      setError(getApiErrorMessage(cause, '功能开关保存失败'));
      throw cause;
    } finally {
      setUpdating(false);
    }
  }, [snapshot]);

  const isEnabled = useCallback((key: FeatureKey) => {
    if (!snapshot) return false;
    return snapshot.effective[key] === true;
  }, [snapshot]);

  const value = useMemo<FeatureFlagsContextValue>(() => ({
    snapshot,
    loading,
    updating,
    error,
    runtimeApply,
    isAdmin,
    load,
    update,
    isEnabled,
  }), [error, isAdmin, isEnabled, load, loading, runtimeApply, snapshot, update, updating]);

  return (
    <FeatureFlagsContext.Provider value={value}>
      {children}
    </FeatureFlagsContext.Provider>
  );
};

export const useFeatureFlags = (): FeatureFlagsContextValue => {
  const value = useContext(FeatureFlagsContext);
  if (!value) throw new Error('useFeatureFlags 必须在 FeatureFlagsProvider 内使用');
  return value;
};

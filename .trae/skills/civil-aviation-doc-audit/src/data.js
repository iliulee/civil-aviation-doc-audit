// src/data.js —— 工作台数据层（纯浏览器 API，无外部依赖）
// 能力：双模加载（HTTP fetch / File System Access API）+ IndexedDB 句柄持久化 + 原子写 + 自动备份
export const WB = {
  index: null, foundationDirHandle: null, indexFileHandle: null,
  loadMode: null, onDataLoaded: null,
  DB_NAME: 'wb_handles', STORE: 'handles', KEY: 'last_foundation_dir',
};

function _idbOpen() {
  return new Promise((res, rej) => {
    const rq = indexedDB.open(WB.DB_NAME, 1);
    rq.onupgradeneeded = () => rq.result.createObjectStore(WB.STORE);
    rq.onsuccess = () => res(rq.result);
    rq.onerror = () => rej(rq.error);
  });
}

async function saveDirHandle(h) {
  const db = await _idbOpen();
  await new Promise((res, rej) => {
    const tx = db.transaction(WB.STORE, 'readwrite');
    tx.objectStore(WB.STORE).put(h, WB.KEY);
    tx.oncomplete = res; tx.onerror = () => rej(tx.error);
  });
  db.close();
}

// v1 用；v2 并入时编辑器复用。恢复上次授权目录句柄，一键重载项目。
export async function restoreLastHandle() {
  try {
    const db = await _idbOpen();
    const h = await new Promise((res, rej) => {
      const rq = db.transaction(WB.STORE, 'readonly').objectStore(WB.STORE).get(WB.KEY);
      rq.onsuccess = () => res(rq.result); rq.onerror = () => rej(rq.error);
    });
    db.close();
    if (!h) return false;
    const p = await h.queryPermission({ mode: 'readwrite' });
    if (p !== 'granted') { if (await h.requestPermission({ mode: 'readwrite' }) !== 'granted') return false; }
    await _loadFromHandle(h); return true;
  } catch { return false; }
}

export async function pickProjectFolder() {
  if (!window.showDirectoryPicker) return false;
  try {
    const root = await window.showDirectoryPicker();
    let fdir = await root.getDirectoryHandle('数据底座').catch(() => null);
    let idx = fdir ? await fdir.getFileHandle('index.json').catch(() => null) : null;
    if (!idx && fdir) { idx = await fdir.getFileHandle('index.json').catch(() => null); }
    if (!idx) { fdir = root; idx = await root.getFileHandle('index.json').catch(() => null); }
    if (!idx) return false;
    await _loadFromHandle(fdir, idx);
    await saveDirHandle(fdir);
    return true;
  } catch { return false; }
}

async function _loadFromHandle(fdir, idx) {
  const fh = idx || await fdir.getFileHandle('index.json');
  const file = await fh.getFile();
  WB.index = JSON.parse(await file.text());
  WB.foundationDirHandle = fdir; WB.indexFileHandle = fh; WB.loadMode = 'fsapi';
  try { localStorage.setItem('last_loaded_project', WB.index.project_name || ''); } catch (e) {}
  if (WB.onDataLoaded) WB.onDataLoaded();
}

// HTTP 模式（Vite dev server / 部署后 fetch）直读 index.json
export async function autoLoad() {
  try {
    const r = await fetch('./index.json', { cache: 'no-store' });
    if (r.ok) { WB.index = await r.json(); WB.loadMode = 'fetch';
      if (WB.onDataLoaded) WB.onDataLoaded(); return true; }
  } catch { /* file:// 属正常 */ }
  return false;
}

// 原子写 + 自动备份：仅在有目录句柄（File System Access API 写回）时可写
export async function atomicWriteJSON(filename, obj) {
  if (!WB.foundationDirHandle) throw new Error('未持有目录句柄');
  const fh = await WB.foundationDirHandle.getFileHandle(filename, { create: true });
  const prev = await fh.getFile();
  if (prev.size > 0) {
    try {
      const bdir = await WB.foundationDirHandle.getDirectoryHandle('backups', { create: true });
      const w = await (await bdir.getFileHandle(filename + '.bak', { create: true })).createWritable();
      await w.write(await prev.arrayBuffer()); await w.close();
    } catch (e) { /* 备份失败不阻断 */ }
  }
  const w = await fh.createWritable();
  await w.write(JSON.stringify(obj, null, 2)); await w.close();
}
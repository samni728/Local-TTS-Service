chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'read-selection',
    title: '朗读选中文本',
    contexts: ['selection']
  });
  chrome.contextMenus.create({
    id: 'read-page',
    title: '朗读整页内容',
    contexts: ['page']
  });
});

async function capture(tabId, func) {
  const [{ result }] = await chrome.scripting.executeScript({ target: { tabId }, func });
  return result;
}

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === 'read-selection') {
    const text = await capture(tab.id, () => window.getSelection().toString());
    chrome.storage.local.set({ pendingText: text || '' }, () => chrome.action.openPopup());
  } else if (info.menuItemId === 'read-page') {
    const text = await capture(tab.id, () => document.body.innerText);
    chrome.storage.local.set({ pendingText: text || '' }, () => chrome.action.openPopup());
  }
});

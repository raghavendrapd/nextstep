// Background service worker for NextStep AI Chrome Extension

// Handle messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getTabInfo') {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) {
        sendResponse({
          tabId: tabs[0].id,
          title: tabs[0].title,
          url: tabs[0].url
        });
      }
    });
    return true;
  }
  
  if (request.action === 'analyzeTranscript') {
    analyzeWithBackend(request.transcript, request.apiUrl)
      .then(result => sendResponse({ success: true, result }))
      .catch(error => sendResponse({ success: false, error: error.message }));
    return true;
  }
});

// Analyze transcript with backend
async function analyzeWithBackend(transcript, apiUrl) {
  const response = await fetch(`${apiUrl}/analyze`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ transcript })
  });
  
  if (!response.ok) {
    throw new Error('Analysis failed');
  }
  
  return await response.json();
}

// Listen for tab updates to detect meeting tabs
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url) {
    const isMeetingTab = 
      tab.url.includes('zoom.us') ||
      tab.url.includes('meet.google.com') ||
      tab.url.includes('teams.microsoft.com') ||
      tab.url.includes('webex.com');
    
    if (isMeetingTab) {
      // Could show extension badge or notification here
      chrome.action.setBadgeText({ text: 'LIVE', tabId });
      chrome.action.setBadgeBackgroundColor({ color: '#50eede', tabId });
    }
  }
});

// Remove badge when tab is closed
chrome.tabs.onRemoved.addListener((tabId) => {
  chrome.action.setBadgeText({ text: '', tabId });
});

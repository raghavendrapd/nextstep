// Content script for NextStep AI Chrome Extension
// Runs on all pages to enable audio capture

console.log('NextStep AI Extension loaded');

// Listen for messages from background script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'ping') {
    sendResponse({ status: 'ok' });
  }
  
  if (request.action === 'checkMeeting') {
    const isMeeting = checkIfMeetingActive();
    sendResponse({ isMeeting });
  }
  
  return true;
});

// Check if a meeting is active on current page
function checkIfMeetingActive() {
  const url = window.location.href;
  const title = document.title.toLowerCase();
  
  // Zoom detection
  if (url.includes('zoom.us')) {
    return {
      platform: 'Zoom',
      active: title.includes('meeting') || title.includes('zoom') || document.querySelector('[aria-label*="mute"]') !== null
    };
  }
  
  // Google Meet detection
  if (url.includes('meet.google.com')) {
    return {
      platform: 'Google Meet',
      active: !title.includes('ended') && document.querySelector('[aria-label*="mute"]') !== null
    };
  }
  
  // Microsoft Teams detection
  if (url.includes('teams.microsoft.com')) {
    return {
      platform: 'Microsoft Teams',
      active: title.includes('call') || document.querySelector('[aria-label*="mute"]') !== null
    };
  }
  
  return { platform: 'Unknown', active: false };
}

// Inject audio analysis script if needed
function injectAudioAnalyzer() {
  const script = document.createElement('script');
  script.src = chrome.runtime.getURL('audio-analyzer.js');
  script.onload = () => script.remove();
  (document.head || document.documentElement).appendChild(script);
}

// Auto-inject if on meeting platform
const currentUrl = window.location.href;
if (
  currentUrl.includes('zoom.us') ||
  currentUrl.includes('meet.google.com') ||
  currentUrl.includes('teams.microsoft.com') ||
  currentUrl.includes('webex.com')
) {
  injectAudioAnalyzer();
}

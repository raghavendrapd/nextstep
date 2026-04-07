let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let stream = null;
let timerInterval = null;
let seconds = 0;
let capturedTabId = null;

// Configuration
const API_URL = ''; // Will be set by user
const BACKEND_URL = 'https://your-nextstep-service.onrender.com'; // Replace with actual URL

async function startCapture() {
  const statusIndicator = document.getElementById('statusIndicator');
  const statusText = document.getElementById('statusText');
  const startBtn = document.getElementById('startBtn');
  const stopBtn = document.getElementById('stopBtn');
  const errorContainer = document.getElementById('errorContainer');
  
  errorContainer.innerHTML = '';
  
  try {
    // Get available tabs
    const tabs = await chrome.tabs.query({});
    
    // Find meeting tabs
    const meetingTabs = tabs.filter(tab => {
      const url = tab.url || '';
      return url.includes('zoom.us') || 
             url.includes('meet.google.com') || 
             url.includes('teams.microsoft.com') ||
             url.includes('webex.com');
    });
    
    // If no meeting tabs found, try to capture current active tab
    let tabToCapture;
    
    if (meetingTabs.length > 0) {
      // Use the first meeting tab found
      tabToCapture = meetingTabs[0];
    } else {
      // Ask user to select a tab
      const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
      tabToCapture = activeTab;
      
      // Verify user wants to capture this tab
      if (!confirm(`Capture audio from "${activeTab.title}"?\n\nMake sure the meeting/call is active in this tab.`)) {
        return;
      }
    }
    
    statusText.textContent = 'Requesting permission...';
    
    // Capture audio from tab
    try {
      stream = await chrome.tabCapture.capture({
        audio: true,
        video: false
      });
    } catch (e) {
      // Fallback: try with specific tab
      stream = await chrome.tabs.captureAudio({ tabId: tabToCapture.id });
    }
    
    if (!stream) {
      throw new Error('Failed to capture audio. Please grant microphone permissions.');
    }
    
    capturedTabId = tabToCapture.id;
    audioChunks = [];
    isRecording = true;
    
    // Create MediaRecorder
    const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4';
    mediaRecorder = new MediaRecorder(stream, { mimeType });
    
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        audioChunks.push(e.data);
      }
    };
    
    mediaRecorder.start(1000); // Collect data every second
    
    // Update UI
    statusIndicator.classList.add('active', 'recording');
    statusIndicator.classList.remove('recording');
    statusText.textContent = 'Recording from: ' + tabToCapture.title.substring(0, 30);
    startBtn.style.display = 'none';
    stopBtn.style.display = 'flex';
    document.getElementById('timer').classList.add('recording');
    
    // Start timer
    seconds = 0;
    timerInterval = setInterval(updateTimer, 1000);
    
    // Send audio chunks periodically for live transcription
    startLiveTranscription();
    
  } catch (error) {
    console.error('Capture error:', error);
    statusText.textContent = 'Capture failed';
    errorContainer.innerHTML = `
      <div class="error">
        <strong>Error:</strong> ${error.message}<br><br>
        Make sure you're on a Zoom/Meet tab and have granted permissions.
      </div>
    `;
  }
}

function updateTimer() {
  seconds++;
  const mins = Math.floor(seconds / 60).toString().padStart(2, '0');
  const secs = (seconds % 60).toString().padStart(2, '0');
  document.getElementById('timer').textContent = `${mins}:${secs}`;
}

let transcriptionInterval = null;

function startLiveTranscription() {
  transcriptionInterval = setInterval(async () => {
    if (!isRecording || audioChunks.length === 0) return;
    
    // Create audio blob from chunks
    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
    
    // Send for transcription
    try {
      const formData = new FormData();
      formData.append('file', audioBlob, 'audio.webm');
      
      const response = await fetch(`${BACKEND_URL}/transcribe`, {
        method: 'POST',
        body: formData
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.transcript) {
          // Show live transcript preview
          showTranscriptPreview(data.transcript);
        }
      }
    } catch (e) {
      // Silently fail for live transcription
      console.log('Live transcription unavailable:', e.message);
    }
  }, 10000); // Check every 10 seconds
}

function showTranscriptPreview(transcript) {
  let preview = document.getElementById('transcriptPreview');
  if (!preview) {
    preview = document.createElement('div');
    preview.id = 'transcriptPreview';
    preview.className = 'transcript-preview';
    document.getElementById('results').appendChild(preview);
  }
  preview.textContent = transcript.substring(0, 500) + (transcript.length > 500 ? '...' : '');
  document.getElementById('results').style.display = 'block';
}

async function stopCapture() {
  if (!isRecording) return;
  
  const statusIndicator = document.getElementById('statusIndicator');
  const statusText = document.getElementById('statusText');
  const startBtn = document.getElementById('startBtn');
  const stopBtn = document.getElementById('stopBtn');
  const loadingIndicator = document.getElementById('loadingIndicator');
  const resultsDiv = document.getElementById('results');
  const errorContainer = document.getElementById('errorContainer');
  
  isRecording = false;
  clearInterval(timerInterval);
  clearInterval(transcriptionInterval);
  
  if (mediaRecorder) {
    mediaRecorder.stop();
  }
  
  if (stream) {
    stream.getTracks().forEach(track => track.stop());
  }
  
  // Update UI
  statusIndicator.classList.remove('active', 'recording');
  statusText.textContent = 'Processing...';
  stopBtn.style.display = 'none';
  loadingIndicator.style.display = 'flex';
  document.getElementById('timer').classList.remove('recording');
  
  // Wait for last chunk
  await new Promise(resolve => setTimeout(resolve, 500));
  
  // Create final audio blob
  const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
  
  try {
    // Try to transcribe
    const formData = new FormData();
    formData.append('file', audioBlob, 'audio.webm');
    
    // For now, show a message that live transcription needs backend support
    // The main analysis will work through the web app
    
    statusText.textContent = 'Recording complete!';
    loadingIndicator.style.display = 'none';
    
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = `
      <div class="results-header">Recording Complete</div>
      <div class="result-item">
        <div class="result-label">Duration</div>
        <div class="result-value">${formatTime(seconds)}</div>
      </div>
      <div class="result-item">
        <div class="result-label">Next Step</div>
        <div class="result-value">
          Open the NextStep AI web app to analyze this recording. 
          Copy the transcript below and paste it in the web app.
        </div>
      </div>
      <div class="transcript-preview" id="exportTranscript">
        (Transcript will appear here if live transcription is enabled)
      </div>
      <button class="btn btn-primary" style="margin-top: 16px;" onclick="copyToClipboard()">
        📋 Copy for Analysis
      </button>
    `;
    
    startBtn.style.display = 'flex';
    
  } catch (error) {
    console.error('Processing error:', error);
    statusText.textContent = 'Processing failed';
    loadingIndicator.style.display = 'none';
    startBtn.style.display = 'flex';
    errorContainer.innerHTML = `
      <div class="error">
        <strong>Error:</strong> ${error.message}
      </div>
    `;
  }
}

function formatTime(totalSeconds) {
  const mins = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function copyToClipboard() {
  const transcript = document.getElementById('exportTranscript')?.textContent || '';
  navigator.clipboard.writeText(transcript).then(() => {
    alert('Copied! Paste it in the NextStep AI web app.');
  });
}

// Load saved API URL
document.addEventListener('DOMContentLoaded', () => {
  chrome.storage.local.get(['apiUrl'], (result) => {
    if (result.apiUrl) {
      window.BACKEND_URL = result.apiUrl;
    }
  });
});

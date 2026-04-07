# NextStep AI - Chrome Extension

Capture audio from Zoom, Google Meet, and other browser-based meeting platforms for AI analysis.

## Features

- 🎙️ Capture audio from Zoom/Meet directly in browser
- ⏱️ Live recording timer
- 📊 AI-powered call analysis
- 📋 Copy transcript for analysis

## Installation

### Step 1: Update Backend URL

Edit `popup.js` and update the BACKEND_URL:
```javascript
const BACKEND_URL = 'https://your-render-url.onrender.com';
```

### Step 2: Create Icons

Create three PNG icons:
- `icons/icon16.png` (16x16)
- `icons/icon48.png` (48x48)
- `icons/icon128.png` (128x128)

Use teal color (#50eede) on dark background (#131315).

### Step 3: Load Extension in Chrome

1. Open Chrome
2. Go to `chrome://extensions/`
3. Enable "Developer mode" (toggle in top right)
4. Click "Load unpacked"
5. Select the `chrome-extension` folder

### Step 4: Pin the Extension

1. Click the puzzle piece icon in Chrome toolbar
2. Find "NextStep AI"
3. Click the pin icon to keep it visible

## Usage

1. Open Zoom or Google Meet in a browser tab
2. Join/start your meeting
3. Click the NextStep AI extension icon
4. Click "Start Capture"
5. Grant permission to access the tab's audio
6. Let the meeting continue
7. Click "Stop & Analyze" when ready
8. View results or copy transcript

## Troubleshooting

### "Failed to capture audio"

1. Make sure the meeting tab is active
2. Check that Zoom/Meet is open in Chrome (not desktop app)
3. Refresh the meeting page and try again

### "No audio detected"

1. Make sure participants are speaking
2. Check system volume is not muted
3. Ensure meeting audio is not muted in the app

## How It Works

1. Uses Chrome's `tabCapture` API to capture tab audio
2. Records audio using MediaRecorder
3. Sends audio to backend for transcription
4. Backend uses AI to analyze the transcript
5. Results are displayed in the extension popup

## Platform Support

| Platform | Support |
|----------|---------|
| Google Meet | ✅ Full |
| Zoom (Browser) | ✅ Full |
| Microsoft Teams (Browser) | ✅ Full |
| Webex | ✅ Full |
| Zoom Desktop App | ❌ Not supported |
| Phone Calls | ❌ Not supported |

## Privacy

- All audio processing happens locally and on your configured backend
- No audio is sent to third-party servers
- You can review all code in this extension

## License

MIT License

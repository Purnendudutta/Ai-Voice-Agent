# 📦 SHRUTI AI - Desktop Distribution & Sharing Guide

This guide explains how to package and share **SHRUTI AI** with friends, family, or other users so they can run it on their Windows computers, enter their own free Google Gemini API key, and talk with Shruti.

---

## 🚀 Method 1: Instant Portable Share (Recommended & Fastest)

This method lets your friends run Shruti with zero technical setup:

1. **Clean up your personal API key (if any)**:
   Make sure you don't share your private `.env` file with your personal key (unless you intend to share your quota).
2. **Zip the folder**:
   Send the project zip file to your friend.
3. **What your friend does**:
   1. Extracts the `.zip` file anywhere (e.g. `Downloads` or `Desktop`).
   2. Double-clicks **`Run_Shruti.bat`** (or runs `Create_Desktop_Shortcut.bat` to add a desktop icon).
   3. The script automatically sets up the environment, launches Shruti, and opens the native desktop app window.
   4. A friendly **Welcome to Shruti AI** screen pops up asking for their **Google Gemini API Key**:
      - They paste their free key (link to Google AI Studio is right on screen).
      - They click **Connect & Start Talking**.
   5. Shruti connects immediately and starts listening!

---

## 🛠️ Method 2: Compile a Standalone Executable (.exe)

If you want a standalone folder that doesn't require users to install Python manually:

1. Open a terminal or double-click:
   ```cmd
   build_executable.bat
   ```
2. PyInstaller will compile everything into:
   ```
   dist/ShrutiAI/ShrutiAI.exe
   ```
3. Zip the **`dist/ShrutiAI`** folder and share that `.zip` with your friends.
4. When they extract it and double-click `ShrutiAI.exe`, it launches directly with no Python installation needed!

---

## 🔑 How Friends Get Their Free API Key

Shruti includes an in-app setup screen:
1. When launched for the first time on any computer without an API key, Shruti automatically displays a welcoming setup modal.
2. Users can get a free API key at [Google AI Studio](https://aistudio.google.com/apikey) with their Google account.
3. They paste it into the UI and click **Connect**.
4. The key is saved locally on their computer in `data/api_key.txt` and `.env` so they only need to enter it once.

---

## ⚙️ In-App API Key Management

Users can also change or update their API key at any time:
1. Click **⚙️ Settings** in the top-right corner of the Shruti dashboard.
2. Scroll to **6. Google Gemini API Key**.
3. Paste the new key and click **Save Key**.

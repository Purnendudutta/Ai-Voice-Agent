# 🌐 SHRUTI AI - Public Web Voice Agent Deployment Guide

This guide explains how to deploy **SHRUTI AI** to the cloud so anyone can open your link on their phone, laptop, or desktop and speak directly with Shruti in real-time using their device's microphone and speakers.

---

## ⚡ Deployment Options Overview

| Platform | Free Tier | Setup Time | Recommended For |
| :--- | :---: | :---: | :--- |
| **Render** | ✅ Yes | 3 minutes | Easiest zero-setup deployment |
| **Railway** | ✅ Yes ($5 free credit) | 2 minutes | Fast Docker builds & instant WebSockets |
| **Hugging Face Spaces** | ✅ Yes (Unlimited) | 3 minutes | Public AI showcases & free hosting |
| **VPS / DigitalOcean / AWS** | ❌ Paid | 5 minutes | Dedicated production servers |

---

## Option 1: Deploy to Render.com (Easiest & Free)

1. Go to [Render.com](https://render.com/) and sign in with your GitHub account.
2. Click **New +** → **Web Service**.
3. Select your repository: `Ai-Voice-Agent`.
4. Render will auto-detect the `Dockerfile`:
   - **Name**: `shruti-voice-agent` (or any name you like)
   - **Environment**: `Docker`
   - **Region**: Choose closest to you (e.g., Singapore, Frankfurt, Oregon)
   - **Instance Type**: `Free`
5. Under **Environment Variables**, add:
   - `GEMINI_API_KEY`: *(Your Google Gemini API Key)*
   - `AGENT_NAME`: `Shruti`
   - `PERSONA_MODE`: `romantic_girlfriend` *(or `assistant`)*
   - `VOICE_NAME`: `Aoede`
6. Click **Deploy Web Service**.
7. In ~2 minutes, Render will give you a public HTTPS URL (e.g. `https://shruti-voice-agent.onrender.com`).
   - Anyone opening that link on their phone or computer can now tap the mic and talk with Shruti!

---

## Option 2: Deploy to Railway.app

1. Go to [Railway.app](https://railway.app/) and sign in with GitHub.
2. Click **New Project** → **Deploy from GitHub repo**.
3. Select `Ai-Voice-Agent`.
4. Click **Add Variables**:
   - `GEMINI_API_KEY` = your API key
5. Railway will automatically build the `Dockerfile` and generate a live public domain under **Settings → Networking → Generate Domain**.

---

## Option 3: Deploy to Hugging Face Spaces (Free Docker)

1. Go to [Hugging Face Spaces](https://huggingface.co/spaces) and click **Create new Space**.
2. Select **Space SDK** → **Docker** (Blank).
3. Connect your GitHub repository or push the code to Hugging Face.
4. Go to **Settings → Variables and Secrets**:
   - Add Secret: `GEMINI_API_KEY` = your API key.
5. Hugging Face builds and hosts your app with a free permanent public URL!

---

## 📱 How Visitors Use the Live Web Agent

1. Visitors open your link (e.g. `https://shruti.yourdomain.com`).
2. They tap **"Say hello or tap to talk"** (or the microphone button).
3. Their browser asks for microphone access (only once).
4. They can immediately speak naturally in English or Hindi (*"Hello Shruti!"*, *"Tum kaisi ho?"*, etc.).
5. Shruti's voice answers in real-time through their device's speakers, with the 3D neon soundwave reacting live!

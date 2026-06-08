---
title: Antigravity Stock Dashboard
emoji: 🚀
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 8080
pinned: false
license: mit
---

# Antigravity — 日本株自動売買 実データダッシュボード

NiceGUI 製の日本株トレーディング・ダッシュボード。**SIMULATION_MODE**（yfinance 実 market data）で、
市場指数・損益推移・保有ポジションを Apple 級の glassmorphism UI で可視化します。

> ⚠️ 実発注（kabu STATION API）はローカルの証券ソフト（localhost:18080）が必須のため、
> 本 Space 上では **シミュレーション（ペーパートレード）＋ 実 market data の可視化のみ** が動作します。
> 実弾自動売買は証券ソフトが動くマシン上で `SIMULATION_MODE=False` にして利用してください。

## 機能
- 実データダッシュボード（市場指数チャート: S&P500 / NASDAQ / Dow をライブ yfinance 取得）
- ui.echart による損益推移 / 保有ポジション評価損益 / VWAP チャート
- Apple / Jony Ive 級の glassmorphism UI（Inter フォント・elevation・slideUp 遷移）
- ペーパートレード・複数戦略管理・銘柄抽出

## 技術スタック
- NiceGUI（Quasar/Vue）+ FastAPI/uvicorn
- yfinance（実 market data）・APScheduler・SQLite

## ローカル起動
```bash
pip install -r requirements.txt
python main.py   # → http://localhost:8080
```

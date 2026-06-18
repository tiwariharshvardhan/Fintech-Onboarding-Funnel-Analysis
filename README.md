# Fintech Onboarding Funnel Analysis

A **product-analyst-style interactive dashboard** that models a fintech user onboarding journey — from landing page to first trade — to surface where users drop off, who drops off, and how long activation takes.

Built with **Streamlit + Plotly** on two synthetic datasets: a *high-friction* baseline and an *optimized* redesign, enabling before/after funnel comparison.

---

## 🚀 Live Demo

**[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://fintech-funnel-analysis.streamlit.app/)**

> Run locally — see [Quick Start](#quick-start) below.

---

## Problem Statement

Fintech platforms lose a significant share of users between sign-up and first activation. This project answers three core product questions:

1. **Where** in the onboarding funnel do users drop off the most?
2. **Who** drops off — by acquisition channel and device type?
3. **How long** does each conversion step take, and where is the slow tail?

---

## Funnel Stages

```
Landing → Sign-up → KYC Verified → Deposit Funded → First Trade (Activation)
```

---

## Features

| Feature | Description |
|---|---|
| **Funnel Visualization** | Plotly funnel chart with step conversion % and absolute drop-off per stage |
| **KPI Dashboard** | Headline metrics: Users Landed, Sign-up Rate, KYC Rate, Activation Rate, Median Time-to-Activate |
| **What-If Simulator** | Adjust any step's conversion rate to project incremental activated users |
| **Segment Breakdown** | Activation rates and step-conversion heatmap sliced by channel and device |
| **Time-to-Convert Table** | Median and P90 conversion time between each consecutive stage |
| **Weekly Cohort Trend** | Activation rate over time by landing cohort |
| **Before/After Compare** | Side-by-side comparison of high-friction vs. optimized onboarding flows |
| **Interactive Filters** | Filter by acquisition channel, device type, and landing date range |

---

## Tech Stack

- **Python 3.10+**
- **Streamlit** — interactive web dashboard
- **Plotly** — funnel, bar, heatmap, and line charts
- **Pandas** — data wrangling and cohort logic
- **NumPy** — statistical computations

---

## Project Structure

```
Fintech-Onboarding-Funnel-Analysis/
├── dashboard.py          # Main Streamlit app
├── high_friction.csv     # Synthetic dataset — current (baseline) onboarding flow
├── optimized.csv         # Synthetic dataset — redesigned (optimized) onboarding flow
└── requirements.txt      # Python dependencies
```

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/tiwariharshvardhan/Fintech-Onboarding-Funnel-Analysis.git
cd Fintech-Onboarding-Funnel-Analysis
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the dashboard

```bash
streamlit run dashboard.py
```

The app will open at `http://localhost:8501` in your browser.

---

## Dataset Schema

Both CSVs (`high_friction.csv`, `optimized.csv`) contain synthetic user journey records with the following columns:

| Column | Description |
|---|---|
| `ts_landing` | Timestamp when the user hit the landing page |
| `ts_signup` | Timestamp of successful sign-up |
| `ts_identity_verification` | Timestamp of KYC completion |
| `ts_deposit` | Timestamp of first deposit |
| `ts_first_trade` | Timestamp of first trade (activation milestone) |
| `channel` | Acquisition channel (e.g., organic, paid, referral) |
| `device` | Device type (e.g., Android, iOS, Desktop) |

Missing timestamps indicate the user dropped off at that stage.

---

## Key Insights (Sample)

- The **KYC step** is typically the biggest drop-off point, particularly for Android users due to camera/document friction.
- **P90 time-to-convert** at the KYC stage reveals a long slow tail — indicative of manual review delays.
- The optimized flow improves overall activation rate significantly, with the largest gains at the Sign-up and KYC stages.
- The **What-If Simulator** demonstrates that fixing the leakiest step yields higher absolute gains than optimizing already-performing steps.

---

## How to Read the Dashboard

- **Funnel chart** — steepest step = highest priority fix
- **Heatmap** — red cells = broken steps for that segment; green = healthy
- **Time-to-convert** — long P90 tails flag slow steps, not just leaky ones
- **Compare Both mode** — read *high friction* as today's flow, *optimized* as a redesigned onboarding; the gap is the product opportunity

---

## License

This project is for portfolio and educational purposes. The datasets are fully synthetic.

# XSP Killer

Standalone **XSP/SPX options** paper monitor extracted from [Cemini](https://github.com/cemini23/Cemini-Financial-Suite).

Two lanes:

| Lane | Role | Schedule |
|------|------|----------|
| **A** | Overnight swing — BB/VWAP mentor playbook, paper entries/exits | Intraday 15m RTH + close window 3:45–4:00 PM ET + morning 9:35–10:30 ET |
| **B** | LEAPS core book — hedge-gap alerts only | Daily 8:00 AM ET |

**No Robinhood orders** by default — log-only paper mode until you enable live RH poll.

## Quick start

```bash
git clone git@github.com:cemini23/xsp-killer.git
cd xsp-killer
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # optional RH creds + Redis

# Lane A intraday scan (paper)
PYTHONPATH=. python3 scripts/lane_a_intraday.py --no-publish

# Lane A entry window
PYTHONPATH=. python3 scripts/lane_a_entry.py --no-publish

# Lane B hedge monitor
PYTHONPATH=. python3 scripts/lane_b_monitor.py --no-publish

pytest
```

## Prod install (systemd)

```bash
sudo ./scripts/install_systemd.sh
sudo systemctl enable --now xsp-killer-lane-a-intraday.timer
sudo systemctl enable --now xsp-killer-lane-a-entry.timer
sudo systemctl enable --now xsp-killer-lane-a-monitor.timer
sudo systemctl enable --now xsp-killer-lane-b-monitor.timer
```

Disable the old Cemini timers after cutover:

```bash
sudo systemctl disable --now cemini-xsp-lane-a-intraday.timer \
  cemini-xsp-lane-a-entry.timer cemini-xsp-lane-a-monitor.timer \
  cemini-xsp-lane-b-monitor.timer
```

## Config

- `config/lane_a_rules.yaml` — DTE, BB/VWAP TA, exit rules, paper entry
- `config/lane_b_rules.yaml` — LEAPS + hedge alerts
- `config/lane_b_state.json` — operator hedge pair links

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `XSP_LANE_A_PAPER_ENTRY` | `true` | Automated paper entries |
| `XSP_LANE_A_RH_POLL` | `false` | Poll Robinhood for live positions |
| `XSP_KILLER_INTEL_DISABLED` | `false` | Skip Redis intel publish |
| `REDIS_HOST` | `127.0.0.1` | Optional Cemini intel bus |

## Mentor playbook (Lane A)

- **Entry:** dump bounces off lower/mid Bollinger Band + VWAP reclaim (1h + 15m confirm)
- **Exit:** pump rejects upper Bollinger Band; max loss; morning cut (suppressed when DTE ≥ 30)
- **Close window:** 3:45–4:00 PM ET still required for close-window entries

See `docs/lane-a-brief.md` and `docs/lane-b-brief.md`.

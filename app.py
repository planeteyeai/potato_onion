
import os
import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from pathlib import Path
import json
import time
import streamlit.components.v1 as components

st.set_page_config(page_title="Potato & Onion Commodity Intelligence", page_icon="🥔", layout="wide")
CONFIG_FILE=Path("config.json")
AGMARKNET_URL="https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
# Public data.gov.in sample key; replace with your own free key from data.gov.in for higher limits.
SAMPLE_API_KEY="579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"
DEFAULT={"refresh_seconds":60,"live_api_url":AGMARKNET_URL,"live_api_token":SAMPLE_API_KEY}
STATIC_FIELDS=["arrival_mt","stock_mt","buyer_demand_mt","quality_score","freight_rs_qtl"]
LIVE_PRICE_FIELDS=["timestamp","market","state","commodity","variety","grade","min_price","modal_price","max_price"]
API_HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36","Accept":"application/json"}
CACHE_FILE=Path("agmarknet_cache.json")
HISTORY_FILE=Path("modal_history.json")
DEMAND_FILE=Path("demand_history.json")
RISK_FILE=Path("risk_history.json")
LOGO_FILE=Path("planeteye_logo.png")

def _secret(name, default=""):
    val=(os.environ.get(name) or "").strip()
    if val: return val
    try:
        return str(st.secrets.get(name, default) or default).strip()
    except Exception:
        return str(default or "").strip()

def cfg():
    c=DEFAULT.copy()
    if CONFIG_FILE.exists():
        try: c={**DEFAULT, **json.loads(CONFIG_FILE.read_text())}
        except: pass
    url=_secret("LIVE_API_URL") or _secret("live_api_url")
    token=_secret("LIVE_API_TOKEN") or _secret("DATA_GOV_IN_API_KEY") or _secret("live_api_token")
    if url: c["live_api_url"]=url
    if token: c["live_api_token"]=token
    if not str(c.get("live_api_url","")).strip(): c["live_api_url"]=AGMARKNET_URL
    if not str(c.get("live_api_token","")).strip(): c["live_api_token"]=SAMPLE_API_KEY
    return c

def save(c): CONFIG_FILE.write_text(json.dumps(c,indent=2))

def _is_agmarknet(url):
    u=(url or "").lower()
    return "api.data.gov.in" in u or "9ef84268-d588-465a-a308-a864a43d0070" in u

def _read_cache():
    if CACHE_FILE.exists():
        try:
            payload=json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            recs=payload.get("records") or []
            if recs: return pd.DataFrame(recs), payload.get("fetched_at","")
        except Exception:
            pass
    return None, None

def _write_cache(records):
    CACHE_FILE.write_text(json.dumps({"fetched_at":datetime.now().isoformat(),"records":records},ensure_ascii=False),encoding="utf-8")

def _agmarknet_page(url, api_key, commodity, offset=0, limit=100):
    params={"api-key":api_key,"format":"json","limit":limit,"offset":offset,"filters[commodity]":commodity}
    r=requests.get(url,params=params,headers=API_HEADERS,timeout=(8,35))
    r.raise_for_status()
    payload=r.json()
    recs=payload.get("records") or payload.get("data") or []
    total=int(payload.get("total") or len(recs) or 0)
    return recs, total, len(recs)

def fetch_agmarknet(url, api_key):
    now=datetime.now()
    cooldown=st.session_state.get("_ag_cooldown")
    if cooldown and now<cooldown:
        cached,_=_read_cache()
        if cached is not None and len(cached): return cached,"cached"
        raise RuntimeError("data.gov.in is temporarily unavailable. Wait a few minutes and refresh.")
    records=[]
    page_size=100
    # Personal keys allow large pages; pull every onion/potato mandi available today.
    try:
        for i,com in enumerate(("Onion","Potato")):
            if i: time.sleep(1.0)
            offset=0
            got=0
            total=None
            while True:
                if offset: time.sleep(0.8)
                recs, page_total, n=_agmarknet_page(url, api_key, com, offset=offset, limit=page_size)
                if total is None: total=page_total
                if not recs: break
                records.extend(recs)
                got+=n
                offset+=n
                if got>=total or n<page_size: break
        if records:
            _write_cache(records)
            st.session_state.pop("_ag_cooldown", None)
            return pd.DataFrame(records),"live"
    except (requests.Timeout, requests.ConnectionError):
        st.session_state["_ag_cooldown"]=now+timedelta(minutes=10)
        cached,_=_read_cache()
        if cached is not None and len(cached): return cached,"cached"
        raise RuntimeError("data.gov.in timed out. Using demo until the government API is reachable.")
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code==429:
            st.session_state["_ag_cooldown"]=now+timedelta(minutes=15)
            cached,_=_read_cache()
            if cached is not None and len(cached): return cached,"cached"
            raise RuntimeError("data.gov.in rate limit (HTTP 429). Wait a few minutes, or use your own free API key.") from e
        cached,_=_read_cache()
        if cached is not None and len(cached): return cached,"cached"
        raise
    cached,_=_read_cache()
    if cached is not None and len(cached): return cached,"cached"
    return pd.DataFrame(),"live"

def _load_history():
    if HISTORY_FILE.exists():
        try:
            h=json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(h,list): return h
        except Exception:
            pass
    return []

def _save_history(hist):
    HISTORY_FILE.write_text(json.dumps(hist[-30:],indent=2),encoding="utf-8")

def _record_modals(onion, potato):
    day=datetime.now().strftime("%Y-%m-%d")
    hist=[h for h in _load_history() if h.get("date")!=day]
    hist.append({"date":day,"onion":round(float(onion or 0),2),"potato":round(float(potato or 0),2)})
    hist=sorted(hist,key=lambda x:x.get("date",""))
    _save_history(hist)
    return hist

def _seven_day_avg(hist, key):
    day=datetime.now().strftime("%Y-%m-%d")
    prev=[float(h[key]) for h in hist if h.get("date")!=day and h.get(key)]
    prev=prev[-7:]
    if prev: return sum(prev)/len(prev)
    vals=[float(h[key]) for h in hist if h.get(key)]
    if len(vals)>=2: return sum(vals[:-1])/len(vals[:-1])
    return None

def _delta_vs7(today, avg, kind):
    if not today or not avg:
        return '<span class="delta">vs 7-day avg — collecting history</span>'
    pct=(today-avg)/avg*100
    arrow="▲" if pct>=0 else "▼"
    if kind=="potato":
        cls="green" if pct>=0 else "red"
    else:
        cls="red" if pct>=0 else "green"
    return f'<span class="{cls}">{arrow} {abs(pct):.1f}% vs 7-day avg</span>'

def _load_json_list(path):
    if path.exists():
        try:
            h=json.loads(path.read_text(encoding="utf-8"))
            if isinstance(h,list): return h
        except Exception:
            pass
    return []

def _save_json_list(path, hist):
    path.write_text(json.dumps(hist,indent=2),encoding="utf-8")

def _record_demand(frame):
    day=datetime.now().strftime("%Y-%m-%d")
    entry={"date":day}
    for com in ("Onion","Potato"):
        x=frame[frame.commodity.str.lower()==com.lower()]
        entry[com.lower()]=round(float(x.buyer_demand_mt.sum()) if len(x) else 0,1)
    hist=[h for h in _load_json_list(DEMAND_FILE) if h.get("date")!=day]
    hist.append(entry)
    hist=sorted(hist,key=lambda x:x.get("date",""))[-60:]
    _save_json_list(DEMAND_FILE, hist)
    return hist

def _demand_ytm(hist, key, today_val):
    day=datetime.now().strftime("%Y-%m-%d")
    prev=[float(h[key]) for h in hist if h.get("date")!=day and h.get(key) is not None]
    yesterday=prev[-1] if prev else max(0.0, today_val*0.97)
    if prev:
        tomorrow=max(0.0, today_val+(today_val-yesterday)*0.55)
    else:
        tomorrow=max(0.0, today_val*1.02)
    return yesterday, today_val, tomorrow

def _record_risk(score_onion, score_potato, mandi_scores=None):
    day=datetime.now().strftime("%Y-%m-%d")
    entry={"date":day,"onion":int(score_onion),"potato":int(score_potato),"mandis":mandi_scores or {}}
    hist=[h for h in _load_json_list(RISK_FILE) if h.get("date")!=day]
    hist.append(entry)
    hist=sorted(hist,key=lambda x:x.get("date",""))[-45:]
    _save_json_list(RISK_FILE, hist)
    return hist

def _series_point(hist_row, key, mkey, today_score, day_i, days, seed):
    if hist_row:
        mandis=hist_row.get("mandis") if isinstance(hist_row.get("mandis"),dict) else {}
        if mkey and mkey in mandis:
            return float(mandis[mkey])
        base=float(hist_row.get(key, today_score))
        if mkey:
            return float(np.clip(base+(hash(mkey+str(hist_row.get("date","")))%7)-3,5,98))
        return base
    drift=(day_i-days/2)*0.55*(1 if key=="onion" else -0.55)
    wobble=((hash(seed)%9)-4)*0.35
    return float(np.clip(today_score+drift+wobble,5,98))

def _dual_risk_chart(hist, oni_today, pot_today, market=None, days=14):
    """One frame with Onion + Potato risk series by day."""
    today=datetime.now().date()
    by_date={h.get("date"):h for h in hist}
    mkey_o=f"Onion|{market}" if market and market!="All mandis" else None
    mkey_p=f"Potato|{market}" if market and market!="All mandis" else None
    rows=[]
    for i in range(days-1,-1,-1):
        d=(today-timedelta(days=i)).strftime("%Y-%m-%d")
        h=by_date.get(d)
        oni=_series_point(h,"onion",mkey_o,oni_today,i,days,f"o{d}{market or ''}")
        pot=_series_point(h,"potato",mkey_p,pot_today,i,days,f"p{d}{market or ''}")
        rows.append({"Day":d,"Onion":round(oni,1),"Potato":round(pot,1)})
    if rows:
        rows[-1]["Onion"]=round(float(oni_today),1)
        rows[-1]["Potato"]=round(float(pot_today),1)
    return pd.DataFrame(rows)

def _dual_price_chart(hist_modal, oni_today, pot_today, days=14):
    """Onion + Potato modal price series from saved modal history + today."""
    today=datetime.now().date()
    by_date={h.get("date"):h for h in hist_modal}
    rows=[]
    for i in range(days-1,-1,-1):
        d=(today-timedelta(days=i)).strftime("%Y-%m-%d")
        h=by_date.get(d)
        if h:
            oni=float(h.get("onion") or oni_today or 0)
            pot=float(h.get("potato") or pot_today or 0)
        else:
            # gentle fill so chart still renders before history accumulates
            oni=float(np.clip((oni_today or 0)*(1+(i-days/2)*0.004),0,1e9))
            pot=float(np.clip((pot_today or 0)*(1+(i-days/2)*-0.003),0,1e9))
        rows.append({"Day":d,"Onion":round(oni,1),"Potato":round(pot,1)})
    if rows:
        rows[-1]["Onion"]=round(float(oni_today or 0),1)
        rows[-1]["Potato"]=round(float(pot_today or 0),1)
    return pd.DataFrame(rows)

def _resample_period(daily_df, period):
    """Aggregate Day/Onion/Potato frame to Daily, Weekly or Monthly buckets."""
    if daily_df is None or daily_df.empty:
        return pd.DataFrame(columns=["Period","Onion","Potato"])
    d=daily_df.copy()
    d["Day"]=pd.to_datetime(d["Day"])
    if period=="Daily":
        out=d.rename(columns={"Day":"Period"})
        out["Period"]=out["Period"].dt.strftime("%d %b")
        return out[["Period","Onion","Potato"]]
    if period=="Weekly":
        d["Period"]=d["Day"].dt.to_period("W").apply(lambda p: p.start_time.strftime("%d %b"))
    else:
        d["Period"]=d["Day"].dt.to_period("M").apply(lambda p: p.start_time.strftime("%b %Y"))
    return d.groupby("Period",as_index=False)[["Onion","Potato"]].mean().round(1)

def _bars_with_trend(wide_df, y_title, show_avg=False, height=300, single_trend=True):
    """Grouped Onion/Potato bars + one clean polyline through EVERY bar top (high & low)."""
    import altair as alt
    if wide_df is None or wide_df.empty:
        st.info("No series yet for this view.")
        return None
    # Flatten to one point per bar so the line hits every high/low cleanly
    rows=[]
    pos=0
    for _,r in wide_df.iterrows():
        period=str(r["Period"])
        for com in ("Onion","Potato"):
            rows.append({"Pos":pos,"Period":period,"Commodity":com,"Value":float(r[com]),"Label":f"{period} · {com}"})
            pos+=1
    long=pd.DataFrame(rows)
    if long.empty:
        return None
    avg_val=float(long["Value"].mean()) if len(long) else 0
    if show_avg:
        st.markdown(
            f'<div style="text-align:right;font-size:16px;font-weight:700;color:#d97706;margin:0 0 8px">'
            f'Avg {avg_val:.1f}</div>',
            unsafe_allow_html=True)
    y_top=float(long["Value"].max())*1.15 if len(long) else 1.0
    y_top=max(y_top,1.0)
    y_scale=alt.Scale(domain=[0,y_top])
    order=list(long["Label"])
    bars=alt.Chart(long).mark_bar(cornerRadiusTopLeft=2,cornerRadiusTopRight=2,opacity=0.9,size=18).encode(
        x=alt.X("Label:N",title=None,sort=order,axis=alt.Axis(labelAngle=-35,labelLimit=140)),
        y=alt.Y("Value:Q",title=y_title,scale=y_scale),
        color=alt.Color("Commodity:N",scale=alt.Scale(domain=["Onion","Potato"],range=["#c53030","#1769aa"]),legend=alt.Legend(orient="top")),
        tooltip=["Period:N","Commodity:N","Value:Q"]
    )
    # straight segments through every bar tip (no curve)
    line=alt.Chart(long).mark_line(
        strokeWidth=2.5,color="#10243e",interpolate="linear",
        point=alt.OverlayMarkDef(size=50,filled=True,fill="#10243e")
    ).encode(
        x=alt.X("Label:N",sort=order),
        y=alt.Y("Value:Q",scale=y_scale),
        tooltip=["Period:N","Commodity:N","Value:Q"]
    )
    layers=[bars,line] if single_trend else [bars]
    if show_avg and len(long):
        avg_df=pd.DataFrame({"avg":[avg_val]})
        layers.append(alt.Chart(avg_df).mark_rule(color="#d97706",strokeWidth=2,strokeDash=[4,4]).encode(y=alt.Y("avg:Q",scale=y_scale)))
    st.altair_chart(alt.layer(*layers).properties(height=height), use_container_width=True)
    return avg_val

def _table_multi_chart(frame, x_col, value_cols, title, top_n=10, height=300, sort_by=None):
    """Same look as risk chart: labeled bars, line on tips, Avg clearly above."""
    import altair as alt
    if frame is None or len(frame)==0:
        st.caption(f"{title}: no table rows to chart.")
        return
    cols=[c for c in value_cols if c in frame.columns]
    if not cols or x_col not in frame.columns:
        return
    d=frame.copy()
    for c in cols:
        d[c]=pd.to_numeric(d[c],errors="coerce").fillna(0.0)
    key=sort_by if sort_by in cols else cols[0]
    d=d.sort_values(key,ascending=False).head(top_n).reset_index(drop=True)
    d["_cat"]=d[x_col].astype(str)
    scaled={}
    for c in cols:
        vals=d[c].astype(float)
        mn,mx=float(vals.min()),float(vals.max())
        scaled[c]=((vals-mn)/(mx-mn)*100.0) if mx>mn else (vals*0.0+50.0)
    rows=[]
    for i in range(len(d)):
        cat=d["_cat"].iloc[i]
        short=cat if len(cat)<=24 else cat[:22]+"…"
        for c in cols:
            nice=c.replace("_"," ").replace("mt","MT").replace("cr","₹ Cr")
            raw=float(d[c].iloc[i])
            val=float(scaled[c].iloc[i])
            if raw<=0:
                continue
            rows.append({
                "Label":f"{short} · {nice}",
                "Category":cat,
                "Metric":nice,
                "Index":val,
                "Raw":raw,
            })
    long=pd.DataFrame(rows)
    if long.empty:
        return
    avg_val=float(long["Index"].mean())
    st.markdown(f'<div class="panel"><h2>{_esc(title)}</h2></div>', unsafe_allow_html=True)
    st.markdown(
        f'<div style="text-align:right;font-size:16px;font-weight:700;color:#d97706;margin:0 0 8px">'
        f'Avg {avg_val:.1f}</div>',
        unsafe_allow_html=True)
    order=list(long["Label"])
    y_top=max(105.0, float(long["Index"].max())*1.15)
    y_scale=alt.Scale(domain=[0,y_top])
    bars=alt.Chart(long).mark_bar(cornerRadiusTopLeft=2,cornerRadiusTopRight=2,opacity=0.9,size=18).encode(
        x=alt.X("Label:N",title=None,sort=order,axis=alt.Axis(labelAngle=-35,labelLimit=140)),
        y=alt.Y("Index:Q",title="Indexed value (0–100)",scale=y_scale),
        color=alt.Color("Metric:N",legend=alt.Legend(orient="top",title=None)),
        tooltip=["Category:N","Metric:N","Raw:Q","Index:Q"]
    )
    line=alt.Chart(long).mark_line(
        strokeWidth=2.5,color="#10243e",interpolate="linear",
        point=alt.OverlayMarkDef(size=50,filled=True,fill="#10243e")
    ).encode(
        x=alt.X("Label:N",sort=order),
        y=alt.Y("Index:Q",scale=y_scale),
        tooltip=["Category:N","Metric:N","Index:Q"]
    )
    avg_df=pd.DataFrame({"avg":[avg_val]})
    rule=alt.Chart(avg_df).mark_rule(color="#d97706",strokeWidth=2,strokeDash=[4,4]).encode(y=alt.Y("avg:Q",scale=y_scale))
    st.altair_chart(alt.layer(bars,line,rule).properties(height=height), use_container_width=True)

def _table_chart(frame, x_col, y_col, title, color_col=None, top_n=18, y_title=None, height=280):
    """Single-metric table chart with zigzag line through actual bar values."""
    _table_multi_chart(frame, x_col, [y_col], title, top_n=top_n, height=height, sort_by=y_col)

def _market_analysis(frame, market, oni_r, pot_r, oni_px, pot_px):
    sub=frame.copy()
    if market and market!="All mandis":
        sub=sub[sub.market.astype(str)==market]
    n=len(sub)
    if n==0:
        return "No mandi rows available for analysis."
    parts=[]
    for com,r,px in (("Onion",oni_r,oni_px),("Potato",pot_r,pot_px)):
        cx=sub[sub.commodity.str.lower()==com.lower()]
        if cx.empty:
            parts.append(f"{com}: no rows in selected market — using overall risk {r}/100.")
            continue
        arr=max(float(cx.arrival_mt.sum()),1)
        dmd=float(cx.buyer_demand_mt.sum())
        ratio=dmd/arr
        mkts=cx.market.nunique()
        tone="tight" if ratio>1.15 else ("loose" if ratio<.75 else "balanced")
        parts.append(
            f"{com}: modal ₹{px:,.0f}/qtl, risk {r}/100, demand/arrival {ratio:.2f}× ({tone}) across {len(cx)} row(s) / {mkts} market(s)."
        )
    return " · ".join(parts)

def _mandi_risk(frame, commodity, market):
    sub=frame[frame.commodity.str.lower()==commodity.lower()]
    if market and market!="All mandis":
        sub=sub[sub.market.astype(str)==market]
    if sub.empty: return risk(frame, commodity)
    return risk(sub, commodity)

def _risk_stock_chart(wide_df):
    """Legacy dual line helper kept for compatibility."""
    import altair as alt
    long=wide_df.melt(id_vars=["Day"],value_vars=["Onion","Potato"],var_name="Commodity",value_name="Risk")
    long["Day"]=pd.to_datetime(long["Day"])
    line=alt.Chart(long).mark_line(strokeWidth=2.8,interpolate="monotone",point=alt.OverlayMarkDef(size=45)).encode(
        x=alt.X("Day:T",title="Day",axis=alt.Axis(format="%d %b",labelAngle=-25,tickCount=7)),
        y=alt.Y("Risk:Q",title="Risk /100",scale=alt.Scale(domain=[0,100])),
        color=alt.Color("Commodity:N",scale=alt.Scale(domain=["Onion","Potato"],range=["#c53030","#1769aa"]),legend=alt.Legend(orient="top")),
        tooltip=["Day:T","Commodity:N","Risk:Q"]
    ).properties(height=300)
    return line.configure_view(strokeWidth=0).configure_axis(grid=True,gridOpacity=0.25)

def _op_metric(frame, col, agg="mean"):
    out={}
    for com in ("Onion","Potato"):
        x=frame[frame.commodity.str.lower()==com.lower()]
        if x.empty or col not in x.columns:
            out[com]=0.0
        elif agg=="sum":
            out[com]=float(x[col].sum())
        else:
            out[com]=float(x[col].mean())
    return out

def _show_op_bars(title, metrics, height=220):
    """Grouped Onion/Potato bar chart. metrics: {label: {"Onion":v,\"Potato\":v}} or single {"Onion\":v,\"Potato\":v}."""
    if not metrics:
        return
    rows=[]
    if set(metrics.keys())>={"Onion","Potato"} and all(not isinstance(v,dict) for v in metrics.values()):
        for com in ("Onion","Potato"):
            rows.append({"Metric":title,"Commodity":com,"Value":float(metrics.get(com,0))})
    else:
        for label,vals in metrics.items():
            if not isinstance(vals,dict): continue
            for com in ("Onion","Potato"):
                rows.append({"Metric":str(label),"Commodity":com,"Value":float(vals.get(com,0))})
    if not rows: return
    cdf=pd.DataFrame(rows)
    st.markdown(f'<div class="panel"><h2>{_esc(title)}</h2></div>', unsafe_allow_html=True)
    try:
        import altair as alt
        chart=(alt.Chart(cdf).mark_bar(cornerRadiusTopLeft=3,cornerRadiusTopRight=3).encode(
            x=alt.X("Metric:N",title=None,axis=alt.Axis(labelAngle=0)),
            xOffset="Commodity:N",
            y=alt.Y("Value:Q",title=None),
            color=alt.Color("Commodity:N",scale=alt.Scale(domain=["Onion","Potato"],range=["#c53030","#1769aa"]),legend=alt.Legend(orient="top")),
            tooltip=["Metric:N","Commodity:N","Value:Q"]
        ).properties(height=height))
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        st.bar_chart(cdf.pivot(index="Metric",columns="Commodity",values="Value"), height=height)

def _report_bytes(df_out, fmt):
    import io
    if fmt=="csv":
        return df_out.to_csv(index=False).encode("utf-8"),"text/csv"
    if fmt=="json":
        return df_out.to_json(orient="records",date_format="iso").encode("utf-8"),"application/json"
    if fmt=="excel":
        buf=io.BytesIO()
        with pd.ExcelWriter(buf,engine="openpyxl") as w:
            df_out.to_excel(w,index=False,sheet_name="Report")
        return buf.getvalue(),"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    # pdf — PlanetEye logo at top, brand name at end
    from fpdf import FPDF
    pdf=FPDF(orientation="L",unit="mm",format="A4")
    pdf.set_auto_page_break(auto=True,margin=14)
    pdf.add_page()
    logo=LOGO_FILE if LOGO_FILE.exists() else Path(__file__).with_name("planeteye_logo.png")
    if logo.exists():
        try:
            pdf.image(str(logo), x=12, y=8, w=32)
        except Exception:
            pass
        pdf.set_xy(50, 14)
    else:
        pdf.set_xy(12, 12)
    pdf.set_font("Helvetica","B",14)
    pdf.cell(0,8,"Potato & Onion Market Report",ln=1)
    pdf.set_font("Helvetica",size=9)
    pdf.set_x(50 if logo.exists() else 12)
    pdf.cell(0,5,f"Generated {datetime.now().strftime('%d-%b-%Y %H:%M')}",ln=1)
    pdf.ln(10)
    pdf.set_font("Helvetica",size=7)
    cols=list(df_out.columns)
    usable=min(len(cols),10)
    cols=cols[:usable]
    w=277/max(usable,1)
    for c in cols:
        pdf.cell(w,6,str(c)[:18],border=1)
    pdf.ln()
    for _,row in df_out.head(80).iterrows():
        for c in cols:
            pdf.cell(w,5,str(row[c])[:18],border=1)
        pdf.ln()
    pdf.ln(10)
    pdf.set_font("Helvetica",size=12)
    pdf.cell(0,8,"PlanetEye Farm-AI",align="C",ln=1)
    out=pdf.output()
    if isinstance(out,bytearray): out=bytes(out)
    elif isinstance(out,str): out=out.encode("latin-1","replace")
    return out,"application/pdf"

def derive_from_live(df):
    """Derive former static columns only from live AGMARKNET price/grade/state fields."""
    d=df.copy()
    g=d.grade.astype(str).str.upper()
    grade_base=np.where(g.str.contains("FAQ|GRADE A|^A$|SPECIAL",regex=True),92,
                np.where(g.str.contains("GRADE B|^B$",regex=True),82,
                np.where(g.str.contains("GRADE C|^C$",regex=True),74,86)))
    band=(d.max_price-d.min_price).clip(lower=1)
    mid=((d.min_price+d.max_price)/2).clip(lower=1)
    pos=((d.modal_price-d.min_price)/band).clip(0,1)
    d["quality_score"]=(grade_base+(pos-0.5)*12).clip(70,98).round(1)
    rel=(band/d.modal_price.clip(lower=1)).clip(0.02,0.8)
    d["arrival_mt"]=(rel*d.modal_price*0.28+120+pos*180).clip(80,2500).round(0)
    cover=(3.2+d.quality_score/25).clip(3,8)
    d["stock_mt"]=(d.arrival_mt*cover).round(0)
    pressure=(d.modal_price/mid).clip(0.7,1.4)
    d["buyer_demand_mt"]=(d.arrival_mt*pressure).round(0)
    freight_map={
        "maharashtra":130,"madhya pradesh":190,"uttar pradesh":170,"gujarat":150,
        "rajasthan":175,"punjab":195,"haryana":180,"karnataka":205,"tamil nadu":225,
        "andhra pradesh":210,"telangana":200,"bihar":185,"west bengal":200,
        "odisha":195,"chhattisgarh":185,"delhi":140,"nct of delhi":140,
    }
    st_key=d.state.astype(str).str.lower().str.strip()
    base=st_key.map(freight_map).fillna(180)
    d["freight_rs_qtl"]=(base+band*0.02+(100-d.quality_score)*0.8).clip(60,320).round(0)
    return d

def demo():
    rng=np.random.default_rng(42); now=datetime.now()
    rows=[]
    markets=[
        ("Lasalgaon","Maharashtra","Onion","Red"),("Pimpalgaon","Maharashtra","Onion","Red"),
        ("Manmad","Maharashtra","Onion","Red"),("Nashik","Maharashtra","Onion","Red"),
        ("Indore","Madhya Pradesh","Potato","Jyoti"),("Agra","Uttar Pradesh","Potato","Chipsona"),
        ("Deesa","Gujarat","Potato","Local"),("Pune","Maharashtra","Potato","Jyoti")]
    base={"Onion":2850,"Potato":2450}
    for m,s,c,v in markets:
        p=base[c]+rng.normal(0,130); arr=max(100,int(rng.normal(700,180)))
        rows.append({"timestamp":now-timedelta(minutes=int(rng.integers(0,120))),
        "market":m,"state":s,"commodity":c,"variety":v,"grade":"A",
        "min_price":round(p-180),"modal_price":round(p),"max_price":round(p+220),
        "arrival_mt":arr,"stock_mt":max(50,int(arr*rng.uniform(2.5,7))),
        "buyer_demand_mt":max(40,int(arr*rng.uniform(.7,1.4))),
        "quality_score":round(rng.uniform(78,96),1),"freight_rs_qtl":round(rng.uniform(60,280))})
    return pd.DataFrame(rows)

def normalize(df):
    df=df.copy(); df.columns=[str(c).strip().lower() for c in df.columns]
    aliases={"date":"timestamp","arrival_date":"timestamp","arrival":"arrival_mt","arrivals":"arrival_mt",
              "modal":"modal_price","market_name":"market","commodity_name":"commodity"}
    df=df.rename(columns={k:v for k,v in aliases.items() if k in df.columns})
    for c in ["commodity","market","state","modal_price"]:
        if c not in df: df[c]="" if c!="modal_price" else 0
    for c in ["min_price","modal_price","max_price","arrival_mt","stock_mt","buyer_demand_mt","quality_score","freight_rs_qtl"]:
        if c not in df: df[c]=0
        df[c]=pd.to_numeric(df[c],errors="coerce").fillna(0)
    if "timestamp" not in df: df["timestamp"]=datetime.now()
    if "variety" not in df: df["variety"]="Unknown"
    if "grade" not in df: df["grade"]="A"
    df["timestamp"]=pd.to_datetime(df["timestamp"],errors="coerce",dayfirst=True).fillna(pd.Timestamp.now())
    df["commodity"]=df["commodity"].astype(str).str.strip()
    df["market"]=df["market"].astype(str).str.strip()
    df["state"]=df["state"].astype(str).str.strip()
    return df

def _empty_meta(demo_df=None, static=None):
    return {"demo":demo_df,"static_fields":static if static is not None else [],"live_fields":LIVE_PRICE_FIELDS,"derived_fields":STATIC_FIELDS}

def load():
    c=st.session_state.config; url=c.get("live_api_url","").strip(); token=(c.get("live_api_token") or "").strip()
    if url:
        try:
            if _is_agmarknet(url):
                raw, freshness=fetch_agmarknet(url, token or SAMPLE_API_KEY)
                d=normalize(raw)
                d=d[d.commodity.str.lower().isin(["onion","potato"])]
                if len(d):
                    d=derive_from_live(d)
                    label="AGMARKNET CACHED" if freshness=="cached" else "AGMARKNET LIVE"
                    if freshness=="cached":
                        st.info("data.gov.in temporarily rate-limited this key. Showing last saved AGMARKNET prices.")
                    return d,label,_empty_meta()
            else:
                h={"Authorization":f"Bearer {token}"} if token else {}
                r=requests.get(url,headers=h,timeout=20); r.raise_for_status(); p=r.json()
                if isinstance(p,dict) and "data" in p: p=p["data"]
                elif isinstance(p,dict) and "records" in p: p=p["records"]
                d=normalize(pd.DataFrame(p))
                if len(d):
                    d=derive_from_live(d)
                    return d,"LIVE API",_empty_meta()
        except Exception as e:
            msg=str(e)
            if "api-key=" in msg or "api.data.gov.in" in msg:
                msg="data.gov.in timed out or is unreachable. Cached mandi prices are used when available."
            st.warning(f"Live API unavailable; demo feed used: {msg}")
    if "uploaded" in st.session_state:
        d=derive_from_live(normalize(st.session_state.uploaded))
        return d,"UPLOADED CSV",_empty_meta()
    return derive_from_live(demo()),"DEMO LIVE",_empty_meta()

def action(r):
    net=r.modal_price-r.freight_rs_qtl-50
    ratio=r.buyer_demand_mt/max(r.arrival_mt,1)
    if ratio>1.15 and r.quality_score>=88: a="BUY / HOLD"
    elif ratio<.75: a="SELL / NEGOTIATE"
    else: a="WATCH"
    return net,a

def risk(d,c):
    x=d[d.commodity.str.lower()==c.lower()]
    if x.empty:return 50
    cv=x.modal_price.std()/max(x.modal_price.mean(),1)
    ratio=x.buyer_demand_mt.sum()/max(x.arrival_mt.sum(),1)
    stock=x.stock_mt.sum()/max(x.arrival_mt.sum(),1)
    return int(np.clip(50+min(25,cv*400)+min(20,max(0,(ratio-1)*30))-min(20,max(0,(stock-5)*3)),0,100))

def _esc(x):
    return str(x).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def _badge(a):
    a=str(a)
    cls="bgreen" if "BUY" in a else ("bred" if "SELL" in a else "borange")
    return f'<span class="badge {cls}">{_esc(a)}</span>'

def _card(label, value, extra="", color=""):
    return f'<div class="card metric"><div class="label">{_esc(label)}</div><div class="value {color}">{value}</div><div class="delta">{extra}</div></div>'

st.session_state.setdefault("config",cfg())
if not str(st.session_state.config.get("live_api_url","")).strip():
    st.session_state.config["live_api_url"]=AGMARKNET_URL
if not str(st.session_state.config.get("live_api_token","")).strip():
    st.session_state.config["live_api_token"]=SAMPLE_API_KEY

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
html,body,.stApp{background:#f4f7fb;color:#172033;font-family:Inter,Arial,sans-serif}
#MainMenu,footer,header[data-testid="stHeader"]{visibility:hidden}
.block-container{padding-top:1.2rem;max-width:1500px}
.poc-header{background:#10243e;color:#fff;padding:20px 28px;border-radius:12px;display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:12px}
.poc-header h1{margin:0;font-size:23px;color:#fff}.poc-header p{margin:5px 0 0;color:#b9c7d8;font-size:13px}
.live{background:#0e9f62;padding:7px 12px;border-radius:20px;font-size:12px;font-weight:700;color:#fff;white-space:nowrap}
.card{background:#fff;border:1px solid #e5e9f0;border-radius:12px;padding:17px;box-shadow:0 2px 8px #17203308}
.metric .label{font-size:12px;color:#687386;letter-spacing:.02em}
.metric .value{font-size:26px;font-weight:800;margin:7px 0}.metric .delta{font-size:12px;color:#687386}
.green{color:#18864b}.orange{color:#d97706}.red{color:#c53030}.purple{color:#6b46c1}
.panel{background:#fff;border:1px solid #e5e9f0;border-radius:12px;padding:18px;margin-bottom:16px}
.panel h2{font-size:16px;margin:0 0 14px;font-weight:700;color:#172033}
.panel h3{font-size:14px;margin:15px 0 8px;font-weight:700;color:#172033}
.panel p{font-size:13px;color:#687386;margin:8px 0 0;line-height:1.45}
.two{display:grid;grid-template-columns:1.3fr .7fr;gap:16px;margin-bottom:16px}
.poc-table{width:100%;border-collapse:collapse;font-size:12px}
.poc-table th,.poc-table td{padding:10px;border-bottom:1px solid #e5e9f0;text-align:left}
.poc-table th{background:#f7f9fc;color:#596579}
.forecast-table{font-size:18px !important}
.forecast-table th,.forecast-table td{padding:14px 12px !important;font-size:18px !important;font-weight:400 !important}
.forecast-table th{font-size:17px !important;font-weight:400 !important}
.demand-table{font-size:16px !important}
.demand-table th,.demand-table td{padding:14px 12px !important;font-size:16px !important;font-weight:600}
.demand-table th{font-size:15px !important;font-weight:700 !important}
.badge{padding:4px 8px;border-radius:12px;font-weight:700;font-size:10px;background:#edf2f7}
.bgreen{background:#e7f7ee;color:#18864b}.borange{background:#fff4df;color:#d97706}.bred{background:#fde9e9;color:#c53030}
.bar{height:12px;background:#e9edf3;border-radius:10px;overflow:hidden}.fill{height:100%;border-radius:10px}
.alert{padding:12px;border-left:4px solid #d97706;background:#fff9ed;border-radius:6px;margin:8px 0;font-size:13px}
.chart{height:230px;display:flex;align-items:flex-end;gap:15px;padding:15px 10px 0;border-bottom:1px solid #ccd4df}
.barcol{flex:1;text-align:center;font-size:11px;color:#687386}.barfill{width:70%;margin:auto;background:#4b83bd;border-radius:5px 5px 0 0}
.barval{font-weight:700;color:#172033;margin-bottom:4px}
.stTabs [data-baseweb="tab-list"]{background:#fff;border-bottom:1px solid #e5e9f0;gap:8px;padding:8px 8px 0}
.stTabs [data-baseweb="tab"]{font-weight:600;color:#566174;border-radius:8px 8px 0 0}
.stTabs [aria-selected="true"]{background:#eaf2fb;color:#1769aa}
@media(max-width:1000px){.two{grid-template-columns:1fr}}
div[data-testid="stSidebar"]{background:#fff}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("Live Controls")
    st.session_state.config["refresh_seconds"]=st.number_input("Refresh seconds",60,3600,int(st.session_state.config["refresh_seconds"]),60)
    st.session_state.config["live_api_url"]=st.text_input("Optional live JSON API URL",st.session_state.config.get("live_api_url",""))
    st.session_state.config["live_api_token"]=st.text_input("API token (optional)",st.session_state.config.get("live_api_token",""),type="password")
    if st.button("Save configuration"): save(st.session_state.config); st.success("Saved")
    up=st.file_uploader("Upload market CSV",type="csv")
    if up:
        st.session_state.uploaded=pd.read_csv(up)
        st.session_state.pop("df_cache", None)
        st.success("CSV loaded")
    st.info("Minimum CSV: commodity, market, state, modal_price. Optional: min_price, max_price, arrival_mt, stock_mt, buyer_demand_mt, quality_score, freight_rs_qtl, variety, grade, timestamp.")

# Keep frame in session so Risk mandi filters don't re-hit AGMARKNET (avoids white/fade reload).
if st.session_state.pop("_force_reload", False) or "df_cache" not in st.session_state:
    with st.spinner("Loading market data…"):
        st.session_state.df_cache=load()
df,source,meta=st.session_state.df_cache
now_s=datetime.now().strftime("%d-%b-%Y %H:%M:%S")
live_on="LIVE" in source and "DEMO" not in source
components.html("""
<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
*{box-sizing:border-box}body{margin:0;font-family:Inter,Arial,sans-serif;background:transparent}
.poc-header{background:#10243e;color:#fff;padding:20px 28px;border-radius:12px;display:flex;justify-content:space-between;align-items:center;gap:20px}
.poc-header h1{margin:0;font-size:23px;color:#fff;font-weight:700}
.poc-header p{margin:5px 0 0;color:#b9c7d8;font-size:13px}
.live{background:#0e9f62;padding:7px 12px;border-radius:20px;font-size:12px;font-weight:700;color:#fff;white-space:nowrap}
</style></head>
<body>
<div class="poc-header">
<div><h1>🥔 🧅 Potato & Onion Commodity Intelligence Command Center</h1>
<p>Live-mode dashboard • Supply • Demand • Price • Storage • Finance • Logistics • Risk</p></div>
<div class="live">● LIVE MODE <span id="clock"></span></div>
</div>
<script>
function clock(){
  var el=document.getElementById('clock');
  if(!el) return;
  el.textContent=' '+new Date().toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
}
setInterval(clock,1000);
clock();
</script>
</body></html>
""", height=96, scrolling=False)

v=df.copy(); z=v.apply(action,axis=1); v["net_realization"]=[q[0] for q in z]; v["action"]=[q[1] for q in z]
pot=df[df.commodity.str.lower()=="potato"]; oni=df[df.commodity.str.lower()=="onion"]
pot_px=float(pot.modal_price.mean()) if len(pot) else 0
oni_px=float(oni.modal_price.mean()) if len(oni) else 0
hist=_record_modals(oni_px, pot_px)
pot_avg=_seven_day_avg(hist,"potato") or (float(pot.modal_price.median()) if len(pot) else None)
oni_avg=_seven_day_avg(hist,"onion") or (float(oni.modal_price.median()) if len(oni) else None)
pot_delta=_delta_vs7(pot_px, pot_avg, "potato")
oni_delta=_delta_vs7(oni_px, oni_avg, "onion")
oni_risk=risk(df,"Onion"); pot_risk=risk(df,"Potato")
fin=df.copy(); fin["inventory_value_cr"]=fin.stock_mt*fin.modal_price*10/1e7
fin["ltv"]=np.where(fin.quality_score>=90,.70,np.where(fin.quality_score>=80,.60,.45))
fin["indicative_finance_cr"]=fin.inventory_value_cr*fin.ltv
fin_cr=float(fin.indicative_finance_cr.sum()); elig_cr=float(fin.inventory_value_cr.sum())
dmd=float(df.buyer_demand_mt.sum()); arr=float(df.arrival_mt.sum())
dmd_pct=(dmd/max(arr,1)-1)*100
stock_mt_total=float(df.stock_mt.sum())
fpo_score=float(df.quality_score.mean()) if len(df) else 0
storage_cap=stock_mt_total*1.45 if stock_mt_total else 0
storage_occ=(stock_mt_total/max(storage_cap,1))*100
storage_avail=max(storage_cap-stock_mt_total,0)
avg_storage_cost=float((80+(100-df.quality_score)*1.1).mean()) if len(df) else 120
HUB={"maharashtra":"Mumbai","madhya pradesh":"Indore","uttar pradesh":"Delhi","gujarat":"Ahmedabad",
     "rajasthan":"Jaipur","punjab":"Ludhiana","haryana":"Delhi","karnataka":"Bengaluru",
     "tamil nadu":"Chennai","delhi":"Delhi","nct of delhi":"Delhi"}
def _hub(state):
    return HUB.get(str(state).lower().strip(),"Nearest hub")
oni_act=v[v.commodity.str.lower()=="onion"]["action"].mode().iloc[0] if len(v[v.commodity.str.lower()=="onion"]) else "WATCH"
pot_act=v[v.commodity.str.lower()=="potato"]["action"].mode().iloc[0] if len(v[v.commodity.str.lower()=="potato"]) else "WATCH"

def _top_state(frame):
    if frame is None or frame.empty or "state" not in frame.columns: return "—"
    counts=frame.state.astype(str).value_counts()
    return str(counts.index[0]) if len(counts) else "—"

def _ratio(frame):
    if frame is None or frame.empty: return 0.0
    return float(frame.buyer_demand_mt.sum())/max(float(frame.arrival_mt.sum()),1)

oni_state=_top_state(oni); pot_state=_top_state(pot)
oni_ratio=_ratio(oni); pot_ratio=_ratio(pot)
oni_lvl="HIGH" if oni_risk>=70 else ("MEDIUM" if oni_risk>=40 else "LOW")
gov_line=f"Monitor onion supply risk in {oni_state} — {oni_risk}/100 {oni_lvl} across {len(oni)} live mandis."

t1,t_mkt,t2,t3,t4,t5,t6=st.tabs(["Command Center","Market & Mandi","Procurement","Finance","Storage & Logistics","Risk & Forecast","Reports"])

with t1:
    c1,c2,c3,c4=st.columns(4)
    c1.markdown(_card("POTATO MODAL PRICE", f"₹{pot_px:,.0f}/qtl" if pot_px else "—", pot_delta), unsafe_allow_html=True)
    c2.markdown(_card("ONION MODAL PRICE", f"₹{oni_px:,.0f}/qtl" if oni_px else "—", oni_delta, "red" if oni_risk>=70 else ""), unsafe_allow_html=True)
    c3.markdown(_card("ESTIMATED MARKET STOCK", f"{stock_mt_total:,.0f} MT", "Derived from live prices × grade"), unsafe_allow_html=True)
    c4.markdown(_card("BUYER DEMAND", f"{dmd_pct:+.1f}%", "Derived demand vs arrivals", "orange"), unsafe_allow_html=True)
    r1,r2,r3,r4=st.columns(4)
    r1.markdown(_card("ONION PRICE RISK", f"{oni_risk}/100", "HIGH • supply/arrival pressure" if oni_risk>=70 else ("MEDIUM" if oni_risk>=40 else "LOW"), "red" if oni_risk>=70 else "orange"), unsafe_allow_html=True)
    r2.markdown(_card("POTATO PRICE RISK", f"{pot_risk}/100", "HIGH" if pot_risk>=70 else ("MEDIUM" if pot_risk>=40 else "LOW"), "orange" if pot_risk>=40 else "green"), unsafe_allow_html=True)
    r3.markdown(_card("STORAGE UTILIZATION", f"{storage_occ:.0f}%", f"Available {storage_avail:,.0f} MT (derived)"), unsafe_allow_html=True)
    r4.markdown(_card("FINANCE OPPORTUNITY", f"₹{fin_cr:,.1f} Cr", "Live modal × derived stock", "purple"), unsafe_allow_html=True)
    left,right=st.columns([1.3,.7])
    snap=v.sort_values("modal_price",ascending=False).head(4)
    mx=max(float(snap.modal_price.max()) if len(snap) else 1,1)
    bars=""
    for _,row in snap.iterrows():
        h=max(20,int(185*float(row.modal_price)/mx))
        bars+=f'<div class="barcol"><div class="barval">₹{row.modal_price:,.0f}</div><div class="barfill" style="height:{h}px"></div>{_esc(row.commodity)}<br>{_esc(row.market)}</div>'
    with left:
        st.markdown(f'<div class="panel"><h2>Market Price Snapshot</h2><div class="chart">{bars or "No mandi rows"}</div></div>', unsafe_allow_html=True)
    with right:
        st.markdown(
            f'<div class="panel"><h2>Decision Engine</h2>'
            f'<div class="alert"><b>🧅 Onion:</b> {_esc(oni_act)} — modal ₹{oni_px:,.0f}/qtl, demand/arrival {oni_ratio:.2f}×, top state {_esc(oni_state)}.</div>'
            f'<div class="alert"><b>🥔 Potato:</b> {_esc(pot_act)} — modal ₹{pot_px:,.0f}/qtl, demand/arrival {pot_ratio:.2f}×, top state {_esc(pot_state)}.</div>'
            f'<div class="alert"><b>🏦 Bank:</b> Finance screening opportunity ₹{fin_cr:,.1f} Cr from current mandi prices × stock.</div>'
            f'<div class="alert"><b>🏛 Government:</b> {_esc(gov_line)}</div></div>',
            unsafe_allow_html=True)
    _show_op_bars("Onion vs Potato — Command Snapshot", {
        "Modal ₹/qtl": _op_metric(df,"modal_price","mean"),
        "Risk /100": {"Onion":float(oni_risk),"Potato":float(pot_risk)},
        "Stock MT": _op_metric(df,"stock_mt","sum"),
        "Demand MT": _op_metric(df,"buyer_demand_mt","sum"),
    })

with t_mkt:
    st.markdown('<div class="panel"><h2>Live Market & Mandi Intelligence</h2></div>', unsafe_allow_html=True)
    fc1,fc2,fc3,fc4=st.columns([1.1,1.1,1.6,.8])
    commodities=["All commodities"]+sorted(v.commodity.dropna().astype(str).unique().tolist())
    com_f=fc1.selectbox("Commodity",commodities)
    states=["All mandi states"]+sorted(v.state.dropna().astype(str).unique().tolist())
    st_f=fc2.selectbox("Market / mandi state",states)
    q=fc3.text_input("Search market/state", placeholder="Search market/state...")
    if fc4.button("↻ Refresh data"):
        st.session_state["_force_reload"]=True
        st.rerun()
    m=v.copy()
    if com_f!="All commodities": m=m[m.commodity.astype(str)==com_f]
    if st_f!="All mandi states": m=m[m.state.astype(str)==st_f]
    if q.strip():
        qq=q.strip().lower()
        m=m[m.market.astype(str).str.lower().str.contains(qq,na=False)|m.state.astype(str).str.lower().str.contains(qq,na=False)]
    st.caption(f"{len(m)} mandi row(s) across {m.market.nunique() if len(m) else 0} markets • all AGMARKNET onion/potato mandis for today")
    body=""
    for _,row in m.iterrows():
        body+=(
            f"<tr><td>{_esc(row.market)}</td><td>{_esc(row.state)}</td><td>{_esc(row.commodity)}</td>"
            f"<td>{_esc(row.variety)}</td><td>{_esc(row.grade)}</td>"
            f"<td>{row.min_price:,.0f}</td><td><b>{row.modal_price:,.0f}</b></td><td>{row.max_price:,.0f}</td>"
            f"<td>{row.arrival_mt:,.0f}</td><td>{row.stock_mt:,.0f}</td><td>{row.quality_score:.0f}</td>"
            f"<td>{_badge(row.action)}</td></tr>"
        )
    st.markdown(
        '<table class="poc-table"><thead><tr><th>Market</th><th>State</th><th>Commodity</th><th>Variety</th>'
        '<th>Grade</th><th>Min</th><th>Modal</th><th>Max</th><th>Arrivals MT</th><th>Stock MT</th>'
        '<th>Quality</th><th>Action</th></tr></thead><tbody>'
        +(body or "<tr><td colspan='12'>No mandis match the filter.</td></tr>")
        +"</tbody></table>",
        unsafe_allow_html=True)
    # One graph from the mandi table (all key columns)
    m_chart=m.copy()
    if len(m_chart):
        m_chart["label"]=m_chart.market.astype(str)+" ("+m_chart.commodity.astype(str)+")"
        _table_multi_chart(
            m_chart,"label",
            ["min_price","modal_price","max_price","arrival_mt","stock_mt","quality_score"],
            "Mandi table — all values",top_n=16,sort_by="modal_price")

with t2:
    st.markdown('<div class="panel"><h2>Bulk Procurement Finder</h2></div>', unsafe_allow_html=True)
    com=st.selectbox("Commodity",["Onion","Potato"]); qty=st.number_input("Required quantity (MT)",100,100000,1000,100)
    mf=st.number_input("Maximum freight ₹/qtl",0,2000,300,10)
    x=df[df.commodity==com].copy(); x["landed_price"]=x.modal_price+x.freight_rs_qtl
    x=x[x.freight_rs_qtl<=mf].sort_values("landed_price")
    st.dataframe(x[["market","state","variety","grade","arrival_mt","stock_mt","modal_price","freight_rs_qtl","landed_price","quality_score"]],use_container_width=True)
    if len(x): st.success(f"Best indicative source: {x.iloc[0].market}, {x.iloc[0].state} — ₹{x.iloc[0].landed_price:,.0f}/qtl landed.")
    # One graph from procurement table rows
    if len(x):
        px=x.head(16).copy()
        px["label"]=px.market.astype(str)+", "+px.state.astype(str)
        _table_multi_chart(
            px,"label",
            ["modal_price","freight_rs_qtl","landed_price","arrival_mt","stock_mt","quality_score"],
            f"Procurement table — all values ({com})",top_n=16,sort_by="landed_price")
    dem_rows=""
    dem_hist=_record_demand(df)
    for com_name in ["Potato","Onion"]:
        cx=df[df.commodity.str.lower()==com_name.lower()]
        if cx.empty: continue
        req=float(cx.buyer_demand_mt.sum())
        yest,tod,tom=_demand_ytm(dem_hist, com_name.lower(), req)
        tgt=float(cx.modal_price.mean())*1.05
        gr=str(cx.grade.mode().iloc[0]) if len(cx.grade.mode()) else "A"
        days=10 if com_name=="Potato" else 15
        seg="Food processor" if com_name=="Potato" else "Retail aggregator"
        dem_rows+=f"<tr><td>{seg}</td><td>{com_name}</td><td>{req:,.0f} MT</td><td>{_esc(gr)}</td><td>{days} days</td><td>₹{tgt:,.0f}/qtl</td></tr>"
        dem_rows+=f"<tr><td colspan='6'><b>{com_name} demand trail:</b> Yesterday {yest:,.0f} MT · Today {tod:,.0f} MT · Tomorrow (est.) {tom:,.0f} MT</td></tr>"
    st.markdown(
        '<div class="panel"><h2>Buyer Demand</h2><table class="poc-table demand-table"><tr><th>Buyer segment</th><th>Commodity</th>'
        '<th>Required</th><th>Grade</th><th>Delivery</th><th>Target</th></tr>'
        +(dem_rows or "<tr><td colspan='6'>No live commodity rows.</td></tr>")+
        '</table><p style="font-size:11px;color:#687386">Yesterday/today/tomorrow estimated from live buyer-demand totals (saved daily; tomorrow from trend).</p></div>',
        unsafe_allow_html=True)
    dem_chart=[]
    for com_name in ["Potato","Onion"]:
        cx=df[df.commodity.str.lower()==com_name.lower()]
        if cx.empty: continue
        req=float(cx.buyer_demand_mt.sum())
        yest,tod,tom=_demand_ytm(dem_hist, com_name.lower(), req)
        dem_chart.append({"Commodity":com_name,"Yesterday":yest,"Today":tod,"Tomorrow":tom,"Target ₹/qtl":float(cx.modal_price.mean())*1.05})
    if dem_chart:
        _table_multi_chart(pd.DataFrame(dem_chart),"Commodity",["Yesterday","Today","Tomorrow","Target ₹/qtl"],"Buyer Demand table — all values",top_n=5,sort_by="Today")

with t3:
    g1,g2,g3,g4=st.columns(4)
    g1.markdown(_card("ELIGIBLE STOCK", f"₹{elig_cr:,.1f} Cr"), unsafe_allow_html=True)
    g2.markdown(_card("INDICATIVE FINANCE", f"₹{fin_cr:,.1f} Cr"), unsafe_allow_html=True)
    g3.markdown(_card("TOP FPO SCORE", f"{fpo_score:.0f}/100", extra="Avg quality from live grade/prices", color="green"), unsafe_allow_html=True)
    g4.markdown(_card("WAREHOUSE STOCK", f"{stock_mt_total:,.0f} MT", "Derived from live feed"), unsafe_allow_html=True)
    x=df.copy(); x["inventory_value_cr"]=x.stock_mt*x.modal_price*10/1e7
    x["ltv"]=np.where(x.quality_score>=90,.70,np.where(x.quality_score>=80,.60,.45))
    x["indicative_finance_cr"]=x.inventory_value_cr*x.ltv
    f=x.groupby(["state","commodity"],as_index=False).agg(stock_mt=("stock_mt","sum"),inventory_value_cr=("inventory_value_cr","sum"),indicative_finance_cr=("indicative_finance_cr","sum"),ltv=("ltv","mean"))
    f=f.sort_values("indicative_finance_cr",ascending=False)
    body=""
    for _,row in f.iterrows():
        s=risk(df, str(row.commodity))
        rlabel="HIGH" if s>=70 else ("MEDIUM-HIGH" if s>=55 else ("MEDIUM" if s>=40 else "LOW"))
        rcls="bred" if rlabel=="HIGH" else ("borange" if "HIGH" in rlabel else "bgreen")
        body+=(
            f"<tr><td>{_esc(row.state)}</td><td>{_esc(row.commodity)}</td><td>{row.stock_mt:,.0f}</td>"
            f"<td>₹{row.inventory_value_cr:,.1f} Cr</td><td>{row.ltv*100:.0f}%</td>"
            f"<td>₹{row.indicative_finance_cr:,.1f} Cr</td><td><span class='badge {rcls}'>{rlabel}</span></td></tr>"
        )
    st.markdown(
        '<div class="panel"><h2>Commodity-backed Finance Screening</h2>'
        '<table class="poc-table"><tr><th>Region</th><th>Commodity</th><th>Stock MT</th>'
        '<th>Indicative value</th><th>LTV</th><th>Finance potential</th><th>Risk</th></tr>'
        +body+
        '</table><p style="font-size:11px;color:#687386">Indicative screening only. Actual lending requires KYC, stock/warehouse verification, insurance, valuation and lender policy.</p></div>',
        unsafe_allow_html=True)
    # Graph from finance screening table
    if len(f):
        f_chart=f.copy()
        f_chart["label"]=f_chart.state.astype(str)+" / "+f_chart.commodity.astype(str)
        _table_multi_chart(
            f_chart,"label",
            ["stock_mt","inventory_value_cr","ltv","indicative_finance_cr"],
            "Finance table — all values",top_n=16,sort_by="indicative_finance_cr")

with t4:
    s1,s2,s3,s4=st.columns(4)
    s1.markdown(_card("TOTAL CAPACITY", f"{storage_cap:,.0f} MT", "Stock × 1.45 buffer (derived)"), unsafe_allow_html=True)
    s2.markdown(_card("OCCUPIED", f"{storage_occ:.0f}%", "Derived from live stock"), unsafe_allow_html=True)
    s3.markdown(_card("AVAILABLE", f"{storage_avail:,.0f} MT", "Derived"), unsafe_allow_html=True)
    s4.markdown(_card("AVG STORAGE COST", f"₹{avg_storage_cost:,.0f}/qtl", "From live quality"), unsafe_allow_html=True)
    st.markdown('<div class="panel"><h2>Storage Economics</h2></div>', unsafe_allow_html=True)
    x=df.copy(); x["storage_cost"]=st.number_input("Storage cost ₹/qtl/month",0,2000,int(max(60,min(400,round(avg_storage_cost)))),10); x["loss_pct"]=st.number_input("Expected loss %",0.0,30.0,max(2.0,min(12.0,round(100-fpo_score,1)/8)),.5)
    x["net_after_storage"]=x.modal_price-x.freight_rs_qtl-x.storage_cost-x.modal_price*x.loss_pct/100
    st.dataframe(x[["market","commodity","stock_mt","modal_price","freight_rs_qtl","storage_cost","loss_pct","net_after_storage"]].sort_values("net_after_storage",ascending=False),use_container_width=True)
    # One graph from storage economics table
    sx=x.sort_values("net_after_storage",ascending=False).head(16).copy()
    if len(sx):
        sx["label"]=sx.market.astype(str)+" ("+sx.commodity.astype(str)+")"
        _table_multi_chart(
            sx,"label",
            ["stock_mt","modal_price","freight_rs_qtl","storage_cost","loss_pct","net_after_storage"],
            "Storage table — all values",top_n=16,sort_by="net_after_storage")
    log_rows=""
    log_data=[]
    for com_name in ["Onion","Potato"]:
        cx=df[df.commodity.str.lower()==com_name.lower()].sort_values("modal_price",ascending=False)
        if cx.empty: continue
        row=cx.iloc[0]
        hub=_hub(row.state)
        qty=max(100,float(row.arrival_mt)*0.6)
        fr=float(row.freight_rs_qtl)
        eta=max(4,int(round(fr/22)))
        route=f"{row.market} → {hub}"
        log_rows+=f"<tr><td>{_esc(row.market)} → {_esc(hub)}</td><td>{com_name}</td><td>{qty:,.0f} MT</td><td>₹{fr:,.0f}/qtl</td><td>{eta}h</td><td>₹{fr:,.0f}/qtl</td></tr>"
        log_data.append({"Route":route,"Commodity":com_name,"Qty MT":qty,"Freight":fr,"ETA h":eta,"Landed impact":fr})
    st.markdown(
        '<div class="panel"><h2>Logistics Intelligence</h2><table class="poc-table"><tr><th>Route</th><th>Commodity</th>'
        '<th>Qty</th><th>Freight</th><th>ETA</th><th>Landed impact</th></tr>'
        +(log_rows or "<tr><td colspan='6'>No live mandi routes.</td></tr>")+
        '</table><p style="font-size:11px;color:#687386">Routes from top live mandis; freight/ETA from live state + price band.</p></div>',
        unsafe_allow_html=True)
    if log_data:
        log_df=pd.DataFrame(log_data)
        log_df["label"]=log_df["Route"].astype(str)+" ("+log_df["Commodity"].astype(str)+")"
        _table_multi_chart(log_df,"label",["Qty MT","Freight","ETA h","Landed impact"],"Logistics table — all values",top_n=10,sort_by="Freight")

with t5:
    def _band(com):
        x=df[df.commodity.str.lower()==com.lower()]
        cur=float(x.modal_price.mean()) if len(x) else 0
        vol=float(x.modal_price.std()) if len(x) else 0
        labels=[]; nums=[]
        for days in [7,15,30]:
            pct=min(.25,max(.03,vol/max(cur,1)*np.sqrt(days/7)*1.8))
            bear,base,bull=round(cur*(1-pct)),round(cur),round(cur*(1+pct))
            labels.append(f"₹{bear:,} / ₹{base:,} / ₹{bull:,}")
            nums.append((bear,base,bull))
        return cur, labels, nums
    oni_lvl="HIGH" if oni_risk>=70 else ("MEDIUM" if oni_risk>=40 else "LOW")
    pot_lvl="HIGH" if pot_risk>=70 else ("MEDIUM" if pot_risk>=40 else "LOW")
    oni_cur,oni_b,oni_n=_band("Onion"); pot_cur,pot_b,pot_n=_band("Potato")
    def _sd(com):
        x=df[df.commodity.str.lower()==com.lower()]
        if x.empty: return f"<b>{com}:</b> no live mandi rows."
        arr=max(float(x.arrival_mt.sum()),1)
        dmd=float(x.buyer_demand_mt.sum())
        ratio=dmd/arr
        px=float(x.modal_price.mean())
        n=len(x)
        if ratio>1.15:
            msg=f"demand {ratio:.2f}× arrivals across {n} mandis — modal ₹{px:,.0f}/qtl, monitor price acceleration."
        elif ratio<.75:
            msg=f"arrivals exceed demand (ratio {ratio:.2f}) across {n} mandis — modal ₹{px:,.0f}/qtl, selective procurement."
        else:
            msg=f"supply-demand balanced (ratio {ratio:.2f}) across {n} mandis — modal ₹{px:,.0f}/qtl, watch spreads."
        return f"<b>{com}:</b> {msg}"
    def _hedge(com, score):
        x=df[df.commodity.str.lower()==com.lower()]
        expo=float((x.stock_mt*x.modal_price*10/1e7).sum()) if len(x) else 0
        lvl="High" if score>=70 else ("Medium" if score>=40 else "Low")
        hedge="60–75%" if score>=70 else ("40–60%" if score>=40 else "20–40%")
        act="REVIEW HEDGE" if score>=70 else ("MONITOR" if score>=40 else "HOLD")
        cls="bred" if score>=70 else ("borange" if score>=40 else "bgreen")
        return expo, hedge, lvl, act, cls
    oni_h=_hedge("Onion", oni_risk); pot_h=_hedge("Potato", pot_risk)
    risk_hist=_record_risk(oni_risk, pot_risk)
    mandi_opts=["All mandis"]+sorted(df.market.dropna().astype(str).unique().tolist())
    g1,g2=st.columns([1.3,.7])
    with g1:
        st.markdown(
            f'<div class="panel"><h2>Price Risk</h2>'
            f'<p>Onion <b style="color:#c53030">{oni_risk}/100 {oni_lvl}</b> · Potato <b style="color:#1769aa">{pot_risk}/100 {pot_lvl}</b> · bars = market data · dashed = trend</p></div>',
            unsafe_allow_html=True)
        rc1,rc2=st.columns(2)
        risk_mandi=rc1.selectbox("Select mandi",mandi_opts,key="risk_mandi_chart")
        risk_period=rc2.selectbox("Trend period",["Daily","Weekly","Monthly"],key="risk_trend_period")
        oni_today=_mandi_risk(df,"Onion",risk_mandi)
        pot_today=_mandi_risk(df,"Potato",risk_mandi)
        # modal for selected mandi (table/market data)
        def _mandi_modal(com):
            sub=df[df.commodity.str.lower()==com.lower()]
            if risk_mandi!="All mandis":
                sub=sub[sub.market.astype(str)==risk_mandi]
            if sub.empty:
                return float(df[df.commodity.str.lower()==com.lower()].modal_price.mean() or 0)
            return float(sub.modal_price.mean())
        oni_px_m=_mandi_modal("Onion"); pot_px_m=_mandi_modal("Potato")
        lookback={"Daily":14,"Weekly":56,"Monthly":180}[risk_period]
        price_daily=_dual_price_chart(hist, oni_px_m, pot_px_m, days=lookback)
        risk_daily=_dual_risk_chart(risk_hist, oni_today, pot_today, market=risk_mandi, days=lookback)
        price_view=_resample_period(price_daily, risk_period)
        risk_view=_resample_period(risk_daily, risk_period)
        st.caption("Price (₹/qtl) — from mandi modal table data")
        try:
            _bars_with_trend(price_view, "Modal ₹/qtl", show_avg=True, height=260)
        except Exception:
            st.bar_chart(price_view.set_index("Period")[["Onion","Potato"]], height=260)
        st.caption("Risk (/100) — average shown above")
        try:
            avg_r=_bars_with_trend(risk_view, "Risk /100", show_avg=True, height=260)
        except Exception:
            st.bar_chart(risk_view.set_index("Period")[["Onion","Potato"]], height=260)
            avg_r=float(pd.concat([risk_view["Onion"],risk_view["Potato"]]).mean()) if len(risk_view) else 0
            st.markdown(
                f'<div style="text-align:right;font-size:16px;font-weight:700;color:#d97706">Avg {avg_r:.1f}</div>',
                unsafe_allow_html=True)
        st.markdown(
            f'<div class="alert"><b>Market analysis ({_esc(risk_mandi)}):</b> {_esc(_market_analysis(df, risk_mandi, oni_today, pot_today, oni_px_m, pot_px_m))}</div>',
            unsafe_allow_html=True)
    with g2:
        st.markdown(f'''
<div class="panel">
  <h2>Supply-Demand Signal</h2>
  <div class="alert">{_sd("Onion")}</div>
  <div class="alert">{_sd("Potato")}</div>
</div>
''', unsafe_allow_html=True)
    # Forecast table + chart of the same table numbers
    st.markdown(f'''
<div class="panel">
  <h2>7 / 15 / 30 Day Scenario Forecast</h2>
  <table class="poc-table forecast-table">
    <tr><th>Commodity</th><th>Current</th><th>7D Bear/Base/Bull</th><th>15D Bear/Base/Bull</th><th>30D Bear/Base/Bull</th></tr>
    <tr><td>Onion</td><td>₹{oni_cur:,.0f}</td><td>{oni_b[0]}</td><td>{oni_b[1]}</td><td>{oni_b[2]}</td></tr>
    <tr><td>Potato</td><td>₹{pot_cur:,.0f}</td><td>{pot_b[0]}</td><td>{pot_b[1]}</td><td>{pot_b[2]}</td></tr>
  </table>
</div>
''', unsafe_allow_html=True)
    forecast_chart=pd.DataFrame([
        {"Period":"Current","Onion":round(oni_cur),"Potato":round(pot_cur)},
        {"Period":"7D base","Onion":oni_n[0][1],"Potato":pot_n[0][1]},
        {"Period":"15D base","Onion":oni_n[1][1],"Potato":pot_n[1][1]},
        {"Period":"30D base","Onion":oni_n[2][1],"Potato":pot_n[2][1]},
    ])
    st.caption("Forecast table on chart (base scenario) — bars + one trend line")
    try:
        _bars_with_trend(forecast_chart, "₹/qtl", show_avg=False, height=240, single_trend=True)
    except Exception:
        st.bar_chart(forecast_chart.set_index("Period")[["Onion","Potato"]], height=240)
    st.markdown(f'''
<div class="panel">
  <h2>Hedge / Exposure Monitor</h2>
  <table class="poc-table">
    <tr><th>Portfolio</th><th>Physical exposure</th><th>Suggested hedge</th><th>Risk</th><th>Action</th></tr>
    <tr><td>Onion inventory</td><td>₹{oni_h[0]:,.2f} Cr</td><td>{oni_h[1]}</td><td>{oni_h[2]}</td><td><span class="badge {oni_h[4]}">{oni_h[3]}</span></td></tr>
    <tr><td>Potato inventory</td><td>₹{pot_h[0]:,.2f} Cr</td><td>{pot_h[1]}</td><td>{pot_h[2]}</td><td><span class="badge {pot_h[4]}">{pot_h[3]}</span></td></tr>
  </table>
</div>
''', unsafe_allow_html=True)
    # Exposure + modal from the hedge/forecast tables — one trend line only
    expo_modal=pd.DataFrame([
        {"Period":"Exposure ₹ Cr","Onion":float(oni_h[0]),"Potato":float(pot_h[0])},
        {"Period":"Modal ₹/qtl","Onion":float(oni_cur),"Potato":float(pot_cur)},
        {"Period":"Risk /100","Onion":float(oni_risk),"Potato":float(pot_risk)},
        {"Period":"7D base ₹","Onion":float(oni_n[0][1]),"Potato":float(pot_n[0][1])},
        {"Period":"15D base ₹","Onion":float(oni_n[1][1]),"Potato":float(pot_n[1][1])},
        {"Period":"30D base ₹","Onion":float(oni_n[2][1]),"Potato":float(pot_n[2][1])},
    ])
    st.caption("Exposure / modal table values — bars + one trend line")
    try:
        _bars_with_trend(expo_modal, "Table value", show_avg=False, height=260, single_trend=True)
    except Exception:
        st.bar_chart(expo_modal.set_index("Period")[["Onion","Potato"]], height=260)

with t6:
    st.markdown('<div class="panel"><h2>Report Center</h2><p>Download daily, weekly or monthly intelligence as CSV, JSON, Excel or PDF.</p></div>', unsafe_allow_html=True)
    x=df.copy(); z=x.apply(action,axis=1); x["net_realization"]=[q[0] for q in z]; x["action"]=[q[1] for q in z]
    cols=["timestamp","market","state","commodity","variety","grade","min_price","modal_price","max_price","arrival_mt","stock_mt","buyer_demand_mt","quality_score","freight_rs_qtl","net_realization","action"]
    p1,p2=st.columns(2)
    period=p1.selectbox("Report period",["Daily","Weekly","Monthly"],key="report_period")
    fmt=p2.selectbox("Download format",["CSV","JSON","Excel","PDF"],key="report_fmt")
    rep=x[cols].copy()
    rep.insert(0,"report_period",period)
    rep.insert(1,"generated_at",datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if period=="Weekly":
        rep=rep.groupby(["report_period","generated_at","commodity","state","market"],as_index=False).agg(
            variety=("variety","first"),grade=("grade","first"),
            min_price=("min_price","mean"),modal_price=("modal_price","mean"),max_price=("max_price","mean"),
            arrival_mt=("arrival_mt","sum"),stock_mt=("stock_mt","sum"),buyer_demand_mt=("buyer_demand_mt","sum"),
            quality_score=("quality_score","mean"),freight_rs_qtl=("freight_rs_qtl","mean"),
            net_realization=("net_realization","mean"),action=("action","first"))
        for c in ["min_price","modal_price","max_price","quality_score","freight_rs_qtl","net_realization"]:
            rep[c]=rep[c].round(1)
    elif period=="Monthly":
        rep=rep.groupby(["report_period","generated_at","commodity","state"],as_index=False).agg(
            markets=("market","nunique"),
            min_price=("min_price","mean"),modal_price=("modal_price","mean"),max_price=("max_price","mean"),
            arrival_mt=("arrival_mt","sum"),stock_mt=("stock_mt","sum"),buyer_demand_mt=("buyer_demand_mt","sum"),
            quality_score=("quality_score","mean"),freight_rs_qtl=("freight_rs_qtl","mean"))
        for c in ["min_price","modal_price","max_price","quality_score","freight_rs_qtl"]:
            rep[c]=rep[c].round(1)
    ext={"CSV":"csv","JSON":"json","Excel":"xlsx","PDF":"pdf"}[fmt]
    mime_key={"CSV":"csv","JSON":"json","Excel":"excel","PDF":"pdf"}[fmt]
    try:
        blob,mime=_report_bytes(rep, mime_key)
        st.download_button(f"Download {period} report ({fmt})",blob,f"{period.lower()}_market_intelligence.{ext}",mime)
    except Exception as e:
        st.warning(f"Could not build {fmt}: {e}. Install openpyxl and fpdf2 if missing.")
    s=x.groupby("commodity").agg(avg_modal=("modal_price","mean"),arrivals_mt=("arrival_mt","sum"),stock_mt=("stock_mt","sum"),demand_mt=("buyer_demand_mt","sum")).reset_index()
    st.dataframe(s,use_container_width=True)
    _show_op_bars("Onion vs Potato — Report Summary", {
        "Modal ₹/qtl": _op_metric(x,"modal_price","mean"),
        "Arrivals MT": _op_metric(x,"arrival_mt","sum"),
        "Stock MT": _op_metric(x,"stock_mt","sum"),
        "Demand MT": _op_metric(x,"buyer_demand_mt","sum"),
    })
    st.download_button("Download Commodity Summary CSV",s.to_csv(index=False).encode(),"commodity_summary.csv","text/csv")
    st.markdown(
        '<table class="poc-table"><tr><th>Report</th><th>Audience</th><th>Frequency</th><th>Purpose</th></tr>'
        '<tr><td>Daily Potato Intelligence</td><td>Farmer/FPO/Buyer</td><td>Daily</td><td>Price, arrivals, stock, demand, action</td></tr>'
        '<tr><td>Daily Onion Intelligence</td><td>Government/Trader/Buyer</td><td>Daily</td><td>Supply, price, storage, risk</td></tr>'
        '<tr><td>Finance Opportunity</td><td>Bank/NABARD ecosystem</td><td>Weekly</td><td>Stock and finance screening</td></tr>'
        '<tr><td>Procurement Opportunity</td><td>Bulk buyers</td><td>Live</td><td>Best source and landed price</td></tr>'
        '<tr><td>Risk & Forecast</td><td>Trader/hedger</td><td>Daily</td><td>Scenario and exposure</td></tr></table>',
        unsafe_allow_html=True)

st.markdown('<p style="text-align:center;color:#778195;padding:25px;font-size:11px">Prototype dashboard • Replace illustrative figures with authenticated official feeds before commercial deployment.</p>', unsafe_allow_html=True)

#!/usr/bin/env python3
"""X-Hack Analyzer (クロスハック) — Tableau-style X Analytics Dashboard"""

import json
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
ANALYSIS_DIR = DATA_DIR / "analysis"

# --- Supabase config (Streamlit Cloud uses st.secrets, local uses env vars) ---
def get_supabase_config():
    """Return (url, key) or (None, None) if not configured."""
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return url, key
    except Exception:
        pass
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
    if url and key:
        return url, key
    return None, None

# === Tableau-inspired theme ===
COLORS = {
    "primary": "#1B2838",
    "accent": "#00D4AA",
    "accent2": "#FF6B6B",
    "accent3": "#4ECDC4",
    "accent4": "#FFE66D",
    "accent5": "#A78BFA",
    "bg": "#0E1117",
    "card": "#1E2A3A",
    "text": "#E8EAED",
    "muted": "#8899AA",
}

PALETTE = [COLORS["accent"], COLORS["accent2"], COLORS["accent4"],
           COLORS["accent5"], COLORS["accent3"], "#FF9F43", "#54A0FF"]

def apply_theme(fig, **overrides):
    """ダークテーマをfigに適用。overridesで上書き可能"""
    defaults = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=COLORS["text"], size=12),
        margin=dict(l=40, r=20, t=50, b=40),
        xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
    )
    defaults.update(overrides)
    fig.update_layout(**defaults)
    return fig

FAVICON_PATH = Path(__file__).parent / "assets" / "favicon.png"
LOGO_PATH = Path(__file__).parent / "assets" / "logo.svg"

st.set_page_config(
    page_title="X-Hack Analyzer",
    page_icon=str(FAVICON_PATH) if FAVICON_PATH.exists() else "⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# === Custom CSS ===
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    .stApp { font-family: 'Inter', sans-serif; }

    /* Header */
    .main-header {
        background: linear-gradient(135deg, #1B2838 0%, #2D3E50 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        border-left: 4px solid #00D4AA;
    }
    .main-header h1 {
        color: #00D4AA;
        font-size: 1.8rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .main-header p {
        color: #8899AA;
        font-size: 0.85rem;
        margin: 0.3rem 0 0 0;
    }

    /* KPI Cards */
    .kpi-container { display: flex; gap: 12px; margin-bottom: 1.5rem; }
    .kpi-card {
        background: linear-gradient(135deg, #1E2A3A 0%, #243447 100%);
        border-radius: 10px;
        padding: 1.2rem 1.5rem;
        flex: 1;
        border-top: 3px solid #00D4AA;
    }
    .kpi-card.alt { border-top-color: #FF6B6B; }
    .kpi-card.alt2 { border-top-color: #A78BFA; }
    .kpi-card .label { color: #8899AA; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; }
    .kpi-card .value { color: #E8EAED; font-size: 1.6rem; font-weight: 700; margin-top: 4px; }
    .kpi-card .delta { font-size: 0.75rem; margin-top: 2px; }
    .kpi-card .delta.up { color: #00D4AA; }
    .kpi-card .delta.down { color: #FF6B6B; }

    /* Section headers */
    .section-header {
        color: #E8EAED;
        font-size: 1.1rem;
        font-weight: 600;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #00D4AA;
        margin: 1.5rem 0 1rem 0;
    }

    /* Data table styling */
    .tweet-card {
        background: #1E2A3A;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 0.5rem;
        border-left: 3px solid #00D4AA;
    }
    .tweet-card .author { color: #00D4AA; font-weight: 600; }
    .tweet-card .metrics { color: #8899AA; font-size: 0.8rem; }
    .tweet-card .text { color: #E8EAED; font-size: 0.9rem; margin-top: 0.3rem; }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #1B2838;
    }
    [data-testid="stSidebar"] .stMarkdown { color: #E8EAED; }

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background: #1E2A3A;
        border-radius: 8px 8px 0 0;
        color: #8899AA;
        padding: 8px 20px;
    }
    .stTabs [aria-selected="true"] {
        background: #243447;
        color: #00D4AA !important;
        border-bottom: 2px solid #00D4AA;
    }

    /* Hide default streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# === Data Loading ===
@st.cache_data(ttl=600)
def load_dataset_supabase(brand: str, url: str, key: str):
    """Load tweets from Supabase."""
    import requests
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    # Fetch all rows (paginated)
    all_rows = []
    limit = 1000
    offset = 0
    while True:
        resp = requests.get(
            f"{url}/rest/v1/xmonitor_tweets",
            headers={**headers, "Prefer": "count=exact"},
            params={
                "brand": f"eq.{brand}",
                "select": "tweet_id,author,text,likes,retweets,replies,views,posted_at,is_official,url",
                "order": "posted_at.desc",
                "limit": limit,
                "offset": offset,
            },
        )
        if resp.status_code != 200:
            break
        rows = resp.json()
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < limit:
            break
        offset += limit

    if not all_rows:
        return None

    df = pd.DataFrame(all_rows)
    df = df.rename(columns={"posted_at": "created_at", "url": "tweet_url"})
    return _process_df(df)


@st.cache_data
def load_dataset_csv(name: str):
    """Load tweets from local CSV."""
    csv_path = DATA_DIR / f"{name}_all.csv"
    if not csv_path.exists():
        return None
    df = pd.read_csv(csv_path)
    return _process_df(df)


def _process_df(df):
    """Common processing for tweet DataFrames."""
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df = df.dropna(subset=["created_at"])
    df["date"] = df["created_at"].dt.date
    df["month"] = df["created_at"].dt.to_period("M").astype(str)
    df["weekday"] = df["created_at"].dt.day_name()
    df["hour"] = df["created_at"].dt.hour
    df["eng_rate"] = ((df["likes"] + df["retweets"] + df["replies"]) / df["views"].clip(lower=1) * 100).round(2)
    if "tweet_url" not in df.columns:
        df["tweet_url"] = "https://x.com/" + df["author"] + "/status/" + df["tweet_id"].astype(str)
    return df


def load_dataset(name: str, brand: str = None):
    """Load dataset from Supabase (if configured) or local CSV."""
    sb_url, sb_key = get_supabase_config()
    if sb_url and sb_key and brand:
        df = load_dataset_supabase(brand, sb_url, sb_key)
        if df is not None:
            return df
    return load_dataset_csv(name)


@st.cache_data(ttl=600)
def load_analysis_supabase(url: str, key: str):
    """Load analysis JSON from Supabase."""
    import requests
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    resp = requests.get(
        f"{url}/rest/v1/xmonitor_analysis",
        headers=headers,
        params={"analysis_type": "eq.latest", "select": "data"},
    )
    if resp.status_code == 200 and resp.json():
        return resp.json()[0]["data"]
    return None


def load_analysis():
    sb_url, sb_key = get_supabase_config()
    if sb_url and sb_key:
        data = load_analysis_supabase(sb_url, sb_key)
        if data:
            return data
    latest = ANALYSIS_DIR / "latest.json"
    if latest.exists():
        with open(latest, encoding="utf-8") as f:
            return json.load(f)
    return None


# === KPI Rendering ===
def render_kpi_cards(df, prev_df=None):
    metrics = [
        ("POSTS", len(df), COLORS["accent"]),
        ("AUTHORS", df["author"].nunique(), COLORS["accent3"]),
        ("LIKES", df["likes"].sum(), COLORS["accent2"]),
        ("RETWEETS", df["retweets"].sum(), COLORS["accent4"]),
        ("REPLIES", df["replies"].sum(), COLORS["accent5"]),
        ("VIEWS", df["views"].sum(), COLORS["accent"]),
    ]

    cols = st.columns(len(metrics))
    for i, (label, value, color) in enumerate(metrics):
        with cols[i]:
            if value >= 1_000_000:
                display = f"{value / 1_000_000:.1f}M"
            elif value >= 1_000:
                display = f"{value / 1_000:.1f}K"
            else:
                display = f"{value:,}"
            st.markdown(f"""
            <div class="kpi-card" style="border-top-color: {color}">
                <div class="label">{label}</div>
                <div class="value">{display}</div>
            </div>
            """, unsafe_allow_html=True)


# === Charts ===
def render_timeline(df):
    daily = df.groupby("date").agg(
        posts=("tweet_id", "count"),
        likes=("likes", "sum"),
        rt=("retweets", "sum"),
        replies=("replies", "sum"),
        views=("views", "sum"),
    ).reset_index()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=daily["date"], y=daily["posts"], name="Posts",
        marker_color=COLORS["accent"], opacity=0.7,
    ))
    fig.add_trace(go.Scatter(
        x=daily["date"], y=daily["likes"], name="Likes",
        yaxis="y2", line=dict(color=COLORS["accent2"], width=2),
    ))
    fig.add_trace(go.Scatter(
        x=daily["date"], y=daily["rt"], name="Retweets",
        yaxis="y2", line=dict(color=COLORS["accent4"], width=1.5, dash="dot"),
    ))
    apply_theme(fig,
        height=380,
        yaxis=dict(title="投稿数", gridcolor="rgba(255,255,255,0.05)"),
        yaxis2=dict(title="エンゲージメント", overlaying="y", side="right", gridcolor="rgba(255,255,255,0.05)"),
        legend=dict(orientation="h", y=1.02, x=0.5, xanchor="center", font=dict(size=11)),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_engagement_breakdown(df):
    """リプ/RT/いいねの比率分析"""
    total_likes = df["likes"].sum()
    total_rt = df["retweets"].sum()
    total_replies = df["replies"].sum()
    total = total_likes + total_rt + total_replies

    col1, col2 = st.columns([1, 2])
    with col1:
        fig = go.Figure(data=[go.Pie(
            labels=["Likes", "Retweets", "Replies"],
            values=[total_likes, total_rt, total_replies],
            marker_colors=[COLORS["accent2"], COLORS["accent4"], COLORS["accent5"]],
            hole=0.55,
            textinfo="percent+label",
            textfont=dict(size=12),
        )])
        apply_theme(fig, height=300, showlegend=False)
        fig.add_annotation(text=f"{total:,}", x=0.5, y=0.5, font=dict(size=18, color=COLORS["text"]), showarrow=False)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # 月別エンゲージメント比率
        monthly = df.groupby("month").agg(
            likes=("likes", "sum"),
            rt=("retweets", "sum"),
            replies=("replies", "sum"),
        ).reset_index()

        fig = go.Figure()
        fig.add_trace(go.Bar(x=monthly["month"], y=monthly["likes"], name="Likes", marker_color=COLORS["accent2"]))
        fig.add_trace(go.Bar(x=monthly["month"], y=monthly["rt"], name="Retweets", marker_color=COLORS["accent4"]))
        fig.add_trace(go.Bar(x=monthly["month"], y=monthly["replies"], name="Replies", marker_color=COLORS["accent5"]))
        apply_theme(fig, height=300, barmode="stack",
                   legend=dict(orientation="h", y=1.02, x=0.5, xanchor="center", font=dict(size=11)))
        st.plotly_chart(fig, use_container_width=True)


def render_post_types(df):
    type_keywords = {
        "キャンペーン": ["キャンペーン", "プレゼント", "抽選", "当選", "応募"],
        "ニュース": ["お知らせ", "リリース", "アップデート", "新機能", "開始"],
        "イベント": ["大会", "イベント", "参加", "開催", "CS", "優勝"],
        "買取・販売": ["買取", "販売", "在庫", "入荷", "価格", "円"],
        "レビュー": ["使ってみ", "便利", "おすすめ", "良い", "最高"],
        "コラボ・PR": ["コラボ", "PR", "提供", "×", "チャンネル"],
    }

    rows = []
    for type_name, keywords in type_keywords.items():
        mask = df["text"].str.contains("|".join(keywords), na=False)
        m = df[mask]
        rows.append({
            "分類": type_name,
            "投稿数": len(m),
            "平均いいね": round(m["likes"].mean(), 1) if len(m) > 0 else 0,
            "平均RT": round(m["retweets"].mean(), 1) if len(m) > 0 else 0,
            "平均リプライ": round(m["replies"].mean(), 1) if len(m) > 0 else 0,
            "平均閲覧数": round(m["views"].mean(), 0) if len(m) > 0 else 0,
            "エンゲージメント率": round(((m["likes"].sum() + m["retweets"].sum() + m["replies"].sum()) / m["views"].clip(lower=1).sum() * 100), 2) if len(m) > 0 else 0,
        })

    type_df = pd.DataFrame(rows)

    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(type_df, x="分類", y="投稿数", title="投稿タイプ分布",
                     color="エンゲージメント率", color_continuous_scale=["#1E2A3A", "#00D4AA"],
                     text="投稿数")
        apply_theme(fig, height=350)
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=type_df["分類"], y=type_df["平均いいね"], name="平均いいね", marker_color=COLORS["accent2"]))
        fig.add_trace(go.Bar(x=type_df["分類"], y=type_df["平均RT"], name="平均RT", marker_color=COLORS["accent4"]))
        fig.add_trace(go.Bar(x=type_df["分類"], y=type_df["平均リプライ"], name="平均リプライ", marker_color=COLORS["accent5"]))
        apply_theme(fig, height=400, barmode="group",
                   title=dict(text="タイプ別 平均エンゲージメント", y=0.95),
                   legend=dict(orientation="h", y=1.02, x=0.5, xanchor="center", font=dict(size=11)),
                   margin=dict(l=40, r=20, t=60, b=80))
        st.plotly_chart(fig, use_container_width=True)


def render_heatmap(df):
    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    weekday_ja = {"Monday": "月", "Tuesday": "火", "Wednesday": "水", "Thursday": "木",
                  "Friday": "金", "Saturday": "土", "Sunday": "日"}

    heatmap = df.groupby(["weekday", "hour"]).size().reset_index(name="count")
    heatmap_pivot = heatmap.pivot(index="weekday", columns="hour", values="count").fillna(0)
    heatmap_pivot = heatmap_pivot.reindex(weekday_order).dropna(how="all")
    heatmap_pivot.index = [weekday_ja.get(d, d) for d in heatmap_pivot.index]

    fig = px.imshow(
        heatmap_pivot,
        color_continuous_scale=[[0, "#1B2838"], [0.4, "#0D6E5B"], [0.7, "#00D4AA"], [1, "#00FFD0"]],
        labels=dict(x="時間", y="曜日", color="投稿数"),
        aspect="auto",
    )
    apply_theme(fig, height=300,
               title=dict(text="投稿ヒートマップ", y=0.95))
    st.plotly_chart(fig, use_container_width=True)


def render_authors(df):
    author_stats = df.groupby("author").agg(
        posts=("tweet_id", "count"),
        likes=("likes", "sum"),
        rt=("retweets", "sum"),
        replies=("replies", "sum"),
        views=("views", "sum"),
        avg_likes=("likes", "mean"),
        avg_eng=("eng_rate", "mean"),
    ).nlargest(20, "posts").reset_index().round(1)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=author_stats["author"], y=author_stats["posts"],
        name="Posts", marker_color=COLORS["accent"], opacity=0.8,
    ))
    fig.add_trace(go.Scatter(
        x=author_stats["author"], y=author_stats["avg_likes"],
        name="Avg Likes", yaxis="y2",
        mode="markers+lines", marker=dict(color=COLORS["accent2"], size=8),
        line=dict(color=COLORS["accent2"], width=1.5),
    ))
    apply_theme(fig, height=400,
        yaxis=dict(title="投稿数", gridcolor="rgba(255,255,255,0.05)"),
        yaxis2=dict(title="平均いいね", overlaying="y", side="right"),
        xaxis_tickangle=-45,
        legend=dict(orientation="h", y=1.02, x=0.5, xanchor="center"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # テーブル
    st.dataframe(
        author_stats[["author", "posts", "likes", "rt", "replies", "views", "avg_likes", "avg_eng"]],
        use_container_width=True, hide_index=True,
        column_config={
            "author": "Author",
            "posts": st.column_config.NumberColumn("Posts", format="%d"),
            "likes": st.column_config.NumberColumn("Total Likes", format="%d"),
            "rt": st.column_config.NumberColumn("Total RT", format="%d"),
            "replies": st.column_config.NumberColumn("Replies", format="%d"),
            "views": st.column_config.NumberColumn("Views", format="%d"),
            "avg_likes": st.column_config.NumberColumn("Avg Likes", format="%.1f"),
            "avg_eng": st.column_config.NumberColumn("Eng Rate %", format="%.2f"),
        },
    )


def render_official(df, official_accounts):
    official = df[df["author"].isin(official_accounts)]
    community = df[~df["author"].isin(official_accounts)]

    if len(official) == 0:
        st.info("No official account data found")
        return

    # KPI comparison
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Official Posts", len(official))
    col2.metric("Avg Likes", f"{official['likes'].mean():.1f}")
    col3.metric("Avg RT", f"{official['retweets'].mean():.1f}")
    col4.metric("Avg Eng Rate", f"{official['eng_rate'].mean():.2f}%")

    # 比較チャート
    metrics = ["likes", "retweets", "replies", "views"]
    labels = ["Likes", "Retweets", "Replies", "Views"]
    off_vals = [official[m].mean() for m in metrics]
    com_vals = [community[m].mean() for m in metrics]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=off_vals, theta=labels, fill="toself", name="Official",
        line_color=COLORS["accent"], fillcolor="rgba(0,212,170,0.2)",
    ))
    fig.add_trace(go.Scatterpolar(
        r=com_vals, theta=labels, fill="toself", name="Community",
        line_color=COLORS["accent2"], fillcolor="rgba(255,107,107,0.2)",
    ))
    apply_theme(fig, height=400,
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(gridcolor="rgba(255,255,255,0.1)", tickfont=dict(size=10)),
            angularaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
        ),
        legend=dict(orientation="h", y=-0.1),
    )
    col1, col2 = st.columns([1, 1])
    with col1:
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        # Top official posts with links
        st.markdown('<div class="section-header">Top Official Posts</div>', unsafe_allow_html=True)
        top = official.nlargest(5, "likes")
        for _, r in top.iterrows():
            url = r.get("tweet_url", f"https://x.com/{r['author']}/status/{r['tweet_id']}")
            st.markdown(f"""
            <div class="tweet-card">
                <span class="author">@{r['author']}</span>
                <span class="metrics"> | ❤️ {r['likes']} | 🔄 {r['retweets']} | 💬 {r['replies']} | 👁️ {r['views']:,}</span>
                <div class="text">{str(r['text'])[:150]}...</div>
                <a href="{url}" target="_blank" style="color: {COLORS['accent']}; font-size: 0.8rem;">Open on X →</a>
            </div>
            """, unsafe_allow_html=True)


def render_top_tweets(df):
    top = df.nlargest(20, "likes")
    for _, r in top.iterrows():
        url = r.get("tweet_url", f"https://x.com/{r['author']}/status/{r['tweet_id']}")
        eng = r.get("eng_rate", 0)
        st.markdown(f"""
        <div class="tweet-card">
            <span class="author">@{r['author']}</span>
            <span class="metrics"> | {r['created_at']:%Y-%m-%d %H:%M} | Eng: {eng:.2f}%</span>
            <br>
            <span class="metrics">❤️ {r['likes']} | 🔄 {r['retweets']} | 💬 {r['replies']} | 👁️ {r['views']:,}</span>
            <div class="text">{str(r['text'])[:200]}</div>
            <a href="{url}" target="_blank" style="color: {COLORS['accent']}; font-size: 0.8rem;">Open on X →</a>
        </div>
        """, unsafe_allow_html=True)


def render_spike_drilldown(df):
    """エンゲージメントスパイク分析 — 跳ねた日のツイートをドリルダウン"""
    import numpy as np

    daily = df.groupby("date").agg(
        posts=("tweet_id", "count"),
        likes=("likes", "sum"),
        rt=("retweets", "sum"),
        replies=("replies", "sum"),
        views=("views", "sum"),
    ).reset_index()
    daily["engagement"] = daily["likes"] + daily["rt"] + daily["replies"]
    daily["eng_rate"] = (daily["engagement"] / daily["views"].clip(lower=1) * 100).round(2)

    # スパイク検出（平均+1σ以上）
    eng_mean = daily["engagement"].mean()
    eng_std = daily["engagement"].std()
    spike_threshold = eng_mean + eng_std
    daily["is_spike"] = daily["engagement"] > spike_threshold

    spike_days = daily[daily["is_spike"]].sort_values("engagement", ascending=False)

    # タイムライン（スパイク強調）
    fig = go.Figure()
    normal = daily[~daily["is_spike"]]
    spikes = daily[daily["is_spike"]]

    fig.add_trace(go.Bar(
        x=normal["date"], y=normal["engagement"], name="通常",
        marker_color=COLORS["accent"], opacity=0.5,
    ))
    fig.add_trace(go.Bar(
        x=spikes["date"], y=spikes["engagement"], name="スパイク",
        marker_color=COLORS["accent2"], opacity=0.9,
        text=[f"L:{r['likes']} RT:{r['rt']}" for _, r in spikes.iterrows()],
        textposition="outside", textfont=dict(size=9),
    ))
    # 閾値ライン
    fig.add_hline(y=spike_threshold, line_dash="dash", line_color=COLORS["muted"],
                  annotation_text=f"スパイク閾値 ({spike_threshold:.0f})",
                  annotation_font_color=COLORS["muted"])

    apply_theme(fig, height=350,
        title=dict(text="エンゲージメントスパイク検出", y=0.95),
        yaxis=dict(title="総エンゲージメント", gridcolor="rgba(255,255,255,0.05)"),
        legend=dict(orientation="h", y=1.02, x=0.5, xanchor="center"),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    if len(spike_days) == 0:
        st.info("スパイクが検出されませんでした。")
        return

    # スパイク日一覧 + 選択
    st.markdown(f"""
    <div style="background: #1E2A3A; padding: 0.8rem 1rem; border-radius: 8px; border-left: 3px solid {COLORS['accent2']}; margin-bottom: 1rem;">
        <span style="color: {COLORS['accent2']}; font-weight: 600;">
            {len(spike_days)}件のスパイク検出
        </span>
        <span style="color: {COLORS['muted']}; font-size: 0.85rem;">
            （閾値: 総エンゲージメント {spike_threshold:.0f} 以上）
        </span>
    </div>
    """, unsafe_allow_html=True)

    # 日付選択
    spike_options = []
    for _, row in spike_days.iterrows():
        label = f"{row['date']} — L:{row['likes']} RT:{row['rt']} ({row['posts']}件)"
        spike_options.append((label, row["date"]))

    selected_label = st.selectbox(
        "スパイク日を選択してドリルダウン",
        options=[opt[0] for opt in spike_options],
        key="spike_select",
    )
    selected_date = spike_options[[opt[0] for opt in spike_options].index(selected_label)][1]

    # 選択された日のツイートを表示
    day_tweets = df[df["date"] == selected_date].sort_values("likes", ascending=False)
    day_stats = daily[daily["date"] == selected_date].iloc[0]

    # 日別サマリー
    cols = st.columns(5)
    cols[0].metric("投稿数", f"{day_stats['posts']}")
    cols[1].metric("いいね", f"{day_stats['likes']:,}")
    cols[2].metric("RT", f"{day_stats['rt']:,}")
    cols[3].metric("リプライ", f"{day_stats['replies']:,}")
    cols[4].metric("エンゲージ率", f"{day_stats['eng_rate']:.2f}%")

    st.markdown(f'<div class="section-header">{selected_date} のツイート（{len(day_tweets)}件）</div>', unsafe_allow_html=True)

    for _, r in day_tweets.iterrows():
        url = r.get("tweet_url", f"https://x.com/{r['author']}/status/{r['tweet_id']}")
        eng = r.get("eng_rate", 0)
        # エンゲージメントに応じたバーの色
        total_eng = r["likes"] + r["retweets"] + r["replies"]
        bar_color = COLORS["accent2"] if total_eng > eng_mean else COLORS["accent"]
        st.markdown(f"""
        <div class="tweet-card" style="border-left-color: {bar_color};">
            <span class="author">@{r['author']}</span>
            <span class="metrics"> | {r['created_at']:%H:%M} | Eng: {eng:.2f}%</span>
            <br>
            <span class="metrics">❤️ {r['likes']} | 🔄 {r['retweets']} | 💬 {r['replies']} | 👁️ {r['views']:,}</span>
            <div class="text">{str(r['text'])[:280]}</div>
            <a href="{url}" target="_blank" style="color: {COLORS['accent']}; font-size: 0.8rem;">Open on X →</a>
        </div>
        """, unsafe_allow_html=True)


def render_content_analysis(df):
    """コンテンツ施策別ディープ分析 — コンサル資料レベル"""
    import re

    df = df.copy()
    df['eng'] = df['likes'] + df['retweets'] + df['replies']
    df['eng_rate'] = (df['eng'] / df['views'].clip(lower=1) * 100).round(2)
    df['text_flat'] = df['text'].fillna('').str.replace('\n', ' ')

    def classify(t):
        if 'CL' in t and '直前' in t:
            if 'サーニーゴ' in t: return 'CL直前企画:サーニーゴ'
            if 'はるn' in t: return 'CL直前企画:はるnチャンネル'
            if 'トレステ' in t: return 'CL直前企画:トレステ綱島'
            if 'さいだん' in t or '大炎上' in t: return 'CL直前企画:さいだんCH'
            return 'CL直前企画:その他'
        if 'インタビュー' in t: return 'インタビュー記事'
        if re.search(r'BOX.*プレゼント|プレゼント.*BOX|1BOX.*当たる|BOX.*当たる|50BOX', t):
            if 'アビスアイ' in t: return 'BOXプレゼント:アビスアイ'
            if 'ニンジャスピナー' in t: return 'BOXプレゼント:ニンジャスピナー'
            if 'MEGAドリーム' in t or 'メガドリーム' in t: return 'BOXプレゼント:MEGAドリーム'
            if '遊戯王' in t: return 'BOXプレゼント:遊戯王OCG'
            return 'BOXプレゼント:その他'
        if re.search(r'デッキ.*プレゼント|プレゼント.*デッキ|優勝デッキ.*当たる', t):
            if 'フーディン' in t: return 'デッキプレゼント:フーディン'
            if 'ミュウツー' in t: return 'デッキプレゼント:ミュウツー'
            if 'ドラパルト' in t and '愛知' in t: return 'デッキプレゼント:CL愛知ドラパ'
            if 'ドラパルト' in t: return 'デッキプレゼント:ドラパルト'
            return 'デッキプレゼント:その他'
        if '最強の' in t and '作れ' in t: return 'UGC企画'
        if '受賞者' in t: return 'UGC企画'
        if '争奪戦' in t or 'BOX争奪' in t: return '争奪戦(店舗コラボ)'
        if 'note' in t.lower() and ('コラボ' in t or 'カドラバ' in t): return 'コラボnote記事'
        if any(k in t for k in ['デッキ分析速報', 'AIデッキ分析', 'AI分析']):
            if 'CL' in t: return 'デッキ分析:CL入賞'
            if 'シティ' in t: return 'デッキ分析:シティ'
            if '海外' in t or 'Regional' in t: return 'デッキ分析:海外'
            return 'デッキ分析:その他'
        if '環境Tier' in t: return '環境Tier速報'
        if '環境シェア' in t: return '環境シェア率'
        if '週間上位デッキ' in t: return 'ガンダム:週間デッキ'
        if 'GCG' in t and 'オススメ' in t: return 'ガンダム:おすすめ'
        if 'キャンペーン' in t and ('DL' in t or '参加' in t): return 'アプリDLキャンペーン'
        if '提供' in t or 'スポンサー' in t: return 'スポンサー・提供'
        return 'その他'

    df['content_type'] = df['text_flat'].apply(classify)

    # 施策別集計
    rows = []
    for ct, grp in df.groupby('content_type'):
        rows.append({
            '施策': ct,
            '投稿数': len(grp),
            '合計L': int(grp['likes'].sum()),
            '合計RT': int(grp['retweets'].sum()),
            '合計V': int(grp['views'].sum()),
            '平均eng率': round(grp['eng_rate'].mean(), 2),
            '平均L': round(grp['likes'].mean(), 1),
            '平均RT': round(grp['retweets'].mean(), 1),
        })
    stats = pd.DataFrame(rows).sort_values('平均eng率', ascending=False)

    # ---- チャート1: 施策別エンゲージメント率バブルチャート ----
    fig = go.Figure()
    for _, r in stats.iterrows():
        fig.add_trace(go.Scatter(
            x=[r['投稿数']], y=[r['平均eng率']],
            mode='markers+text',
            marker=dict(size=max(10, min(60, r['合計RT'] / 50)),
                       color=COLORS['accent'] if 'プレゼント' in r['施策'] or 'CL直前' in r['施策']
                       else COLORS['accent2'] if 'デッキ分析' in r['施策'] or 'インタビュー' in r['施策']
                       else COLORS['accent4'],
                       opacity=0.7),
            text=[r['施策'].split(':')[-1] if ':' in r['施策'] else r['施策']],
            textposition='top center',
            textfont=dict(size=10),
            name=r['施策'],
            hovertemplate=f"<b>{r['施策']}</b><br>投稿数: {r['投稿数']}<br>平均eng率: {r['平均eng率']}%<br>合計RT: {r['合計RT']:,}<extra></extra>",
        ))
    apply_theme(fig, height=450,
        title=dict(text='施策別パフォーマンスマップ', y=0.95),
        xaxis=dict(title='投稿数', gridcolor='rgba(255,255,255,0.05)'),
        yaxis=dict(title='平均エンゲージメント率 (%)', gridcolor='rgba(255,255,255,0.08)'),
        showlegend=False,
    )
    fig.add_annotation(text="バブルサイズ = RT数", xref="paper", yref="paper",
                       x=1, y=1.08, showarrow=False, font=dict(color=COLORS['muted'], size=10))
    st.plotly_chart(fig, use_container_width=True)

    # ---- チャート2: キャンペーン vs コンテンツ比較 ----
    campaign_kw = ['プレゼント', 'CL直前', 'DLキャンペーン', '争奪戦']
    content_kw = ['デッキ分析', 'インタビュー', '環境Tier', 'ガンダム', 'note', 'UGC', '環境シェア']

    camp = stats[stats['施策'].apply(lambda x: any(k in x for k in campaign_kw))]
    cont = stats[stats['施策'].apply(lambda x: any(k in x for k in content_kw))]

    col1, col2 = st.columns(2)
    with col1:
        camp_eng = round((camp['合計L'].sum() + camp['合計RT'].sum()) / max(camp['合計V'].sum(), 1) * 100, 2)
        cont_eng = round((cont['合計L'].sum() + cont['合計RT'].sum()) / max(cont['合計V'].sum(), 1) * 100, 2)

        fig = go.Figure(data=[
            go.Bar(x=['キャンペーン施策', 'コンテンツ施策'],
                   y=[camp_eng, cont_eng],
                   marker_color=[COLORS['accent'], COLORS['accent2']],
                   text=[f'{camp_eng}%', f'{cont_eng}%'],
                   textposition='outside'),
        ])
        apply_theme(fig, height=300,
            title=dict(text='施策カテゴリ別エンゲージメント率', y=0.95),
            yaxis=dict(title='エンゲージメント率 (%)', gridcolor='rgba(255,255,255,0.08)'),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = go.Figure(data=[
            go.Bar(x=['キャンペーン施策', 'コンテンツ施策'],
                   y=[int(camp['合計RT'].sum()), int(cont['合計RT'].sum())],
                   marker_color=[COLORS['accent'], COLORS['accent2']],
                   text=[f"{camp['合計RT'].sum():,}", f"{cont['合計RT'].sum():,}"],
                   textposition='outside'),
        ])
        apply_theme(fig, height=300,
            title=dict(text='施策カテゴリ別 合計RT数', y=0.95),
            yaxis=dict(title='合計RT', gridcolor='rgba(255,255,255,0.08)'),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ---- チャート3: 施策別ランキング（横棒） ----
    top_n = stats.nlargest(15, '平均eng率')
    fig = go.Figure()
    colors = [COLORS['accent'] if any(k in s for k in campaign_kw)
              else COLORS['accent2'] if any(k in s for k in content_kw)
              else COLORS['accent4']
              for s in top_n['施策']]
    fig.add_trace(go.Bar(
        y=top_n['施策'], x=top_n['平均eng率'],
        orientation='h', marker_color=colors,
        text=[f"{v:.2f}% (n={n})" for v, n in zip(top_n['平均eng率'], top_n['投稿数'])],
        textposition='outside',
    ))
    apply_theme(fig, height=500,
        title=dict(text='施策別エンゲージメント率ランキング', y=0.98),
        xaxis=dict(title='平均エンゲージメント率 (%)', gridcolor='rgba(255,255,255,0.05)'),
        margin=dict(l=200, r=80, t=50, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ---- テーブル: 全施策データ ----
    st.markdown(f'<div class="section-header">施策別パフォーマンス一覧</div>', unsafe_allow_html=True)
    st.dataframe(
        stats.rename(columns={
            '施策': '施策名', '投稿数': '件数', '合計L': '合計いいね', '合計RT': '合計リツイート',
            '合計V': '合計閲覧', '平均eng率': 'エンゲージ率%', '平均L': '平均いいね', '平均RT': '平均RT',
        }),
        use_container_width=True, hide_index=True,
    )

    # ---- ドリルダウン: 施策を選択してツイート一覧 ----
    st.markdown(f'<div class="section-header">施策ドリルダウン</div>', unsafe_allow_html=True)
    selected = st.selectbox("施策を選んでツイートを確認",
                            options=stats['施策'].tolist(),
                            key="content_drilldown")
    drill_df = df[df['content_type'] == selected].sort_values('eng', ascending=False)
    st.caption(f"{selected}: {len(drill_df)}件")
    for _, r in drill_df.head(10).iterrows():
        url = r.get("tweet_url", f"https://x.com/{r['author']}/status/{r['tweet_id']}")
        bar_color = COLORS["accent2"] if r['eng_rate'] > 1.0 else COLORS["accent"]
        st.markdown(f"""
        <div class="tweet-card" style="border-left-color: {bar_color};">
            <span class="author">@{r['author']}</span>
            <span class="metrics"> | {r['created_at']:%Y-%m-%d} | Eng: {r['eng_rate']:.2f}%</span>
            <br>
            <span class="metrics">❤️ {r['likes']} | 🔄 {r['retweets']} | 💬 {r['replies']} | 👁️ {r['views']:,}</span>
            <div class="text">{str(r['text'])[:280]}</div>
            <a href="{url}" target="_blank" style="color: {COLORS['accent']}; font-size: 0.8rem;">Open on X →</a>
        </div>
        """, unsafe_allow_html=True)

    # ---- ディープ分析JSONからキーインサイト表示 ----
    deep = None
    sb_url, sb_key = get_supabase_config()
    if sb_url and sb_key:
        import requests as _req
        _resp = _req.get(f"{sb_url}/rest/v1/xmonitor_analysis",
                         headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"},
                         params={"analysis_type": "eq.content_deep", "select": "data"})
        if _resp.status_code == 200 and _resp.json():
            deep = _resp.json()[0]["data"]
    if deep is None:
        deep_path = ANALYSIS_DIR / "content_deep.json"
        if deep_path.exists():
            with open(deep_path, encoding="utf-8") as f:
                deep = json.load(f)
    if deep:
        findings = deep.get("key_findings", [])
        if findings:  # noqa
            st.markdown(f'<div class="section-header">Key Findings</div>', unsafe_allow_html=True)
            for i, finding in enumerate(findings):
                icon = ["💡", "📊", "🏆", "🔥", "📝", "⚠️", "📈"][i % 7]
                st.markdown(f"""
                <div style="background: #1E2A3A; padding: 0.6rem 1rem; border-radius: 8px; margin-bottom: 0.4rem; border-left: 3px solid {COLORS['accent']};">
                    <span style="color: {COLORS['text']}; font-size: 0.9rem;">{icon} {finding}</span>
                </div>
                """, unsafe_allow_html=True)


def render_ai_insights(analysis):
    if analysis is None:
        st.info("AI分析データがありません。Claude Codeセッションで分析を実行してください。")
        return

    # サマリー
    if "summary" in analysis:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1E2A3A, #243447); padding: 1.5rem; border-radius: 10px; border-left: 4px solid {COLORS['accent']}; margin-bottom: 1rem;">
            <p style="color: {COLORS['text']}; font-size: 0.95rem; line-height: 1.6; margin: 0;">{analysis['summary']}</p>
        </div>
        """, unsafe_allow_html=True)

    # ブランド別分析
    for brand_key, brand_label in [("kadoraba", "カドラバ"), ("dmm_myca", "DMM Myca")]:
        brand = analysis.get(brand_key)
        if not brand:
            continue
        st.markdown(f'<div class="section-header">{brand_label} 分析</div>', unsafe_allow_html=True)

        # 概要KPI
        overview = brand.get("概要", {})
        if overview:
            cols = st.columns(4)
            cols[0].metric("総ツイート", f"{overview.get('総ツイート数', 0):,}")
            cols[1].metric("いいね合計", f"{overview.get('いいね合計', 0):,}")
            cols[2].metric("RT合計", f"{overview.get('RT合計', 0):,}")
            cols[3].metric("エンゲージメント率", overview.get("平均エンゲージメント率", "N/A"))

        # 強みと課題
        col1, col2 = st.columns(2)
        with col1:
            for s in brand.get("強み", []):
                st.markdown(f"- :white_check_mark: {s}")
        with col2:
            for w in brand.get("課題", []):
                st.markdown(f"- :warning: {w}")

    # 比較分析
    comp = analysis.get("比較分析", {})
    if comp:
        st.markdown(f'<div class="section-header">比較分析</div>', unsafe_allow_html=True)
        cols = st.columns(3)
        eng = comp.get("エンゲージメント率", {})
        cols[0].metric("エンゲージメント率", f"{eng.get('カドラバ', '')} vs {eng.get('DMM Myca', '')}", eng.get("勝者", ""))
        avg_l = comp.get("平均いいね/投稿", {})
        cols[1].metric("平均いいね/投稿", f"{avg_l.get('カドラバ', '')} vs {avg_l.get('DMM Myca', '')}", avg_l.get("勝者", ""))
        avg_r = comp.get("平均RT/投稿", {})
        cols[2].metric("平均RT/投稿", f"{avg_r.get('カドラバ', '')} vs {avg_r.get('DMM Myca', '')}", avg_r.get("勝者", ""))

        camp = comp.get("キャンペーン効果", {})
        if camp:
            st.info(f"**キャンペーン効果**: {camp.get('分析', '')}")

    # アクションアイテム
    actions = analysis.get("アクションアイテム", [])
    if actions:
        st.markdown(f'<div class="section-header">アクションアイテム</div>', unsafe_allow_html=True)
        for item in actions:
            target = item.get("対象", "")
            color = COLORS["accent"] if target == "カドラバ" else COLORS["accent2"] if target == "DMM Myca" else COLORS["accent4"]
            st.markdown(f"""
            <div style="background: #1E2A3A; padding: 0.8rem 1rem; border-radius: 8px; border-left: 3px solid {color}; margin-bottom: 0.5rem;">
                <span style="color: {color}; font-weight: 600; font-size: 0.8rem;">[{target}]</span>
                <span style="color: {COLORS['text']}; font-size: 0.9rem; font-weight: 600;"> {item.get('提案', '')}</span>
                <br><span style="color: {COLORS['muted']}; font-size: 0.8rem;">{item.get('詳細', '')}</span>
            </div>
            """, unsafe_allow_html=True)

    st.caption(f"分析日: {analysis.get('generated_at', 'N/A')}")


def render_comparison(datasets):
    """複数ブランド比較分析"""
    if len(datasets) < 2:
        st.info("比較にはカドラバ + Myca 両方のデータが必要です。`python collect_myca.py` を実行してください。")
        return

    rows = []
    for name, df in datasets.items():
        rows.append({
            "Brand": name,
            "Posts": len(df),
            "Authors": df["author"].nunique(),
            "Total Likes": df["likes"].sum(),
            "Total RT": df["retweets"].sum(),
            "Total Replies": df["replies"].sum(),
            "Total Views": df["views"].sum(),
            "Avg Likes": round(df["likes"].mean(), 1),
            "Avg RT": round(df["retweets"].mean(), 1),
            "Avg Replies": round(df["replies"].mean(), 1),
            "Avg Eng Rate": round(df["eng_rate"].mean(), 2),
        })
    comp_df = pd.DataFrame(rows)

    # KPI comparison
    st.dataframe(comp_df, use_container_width=True, hide_index=True)

    # Charts
    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure()
        for i, (name, df) in enumerate(datasets.items()):
            monthly = df.groupby("month").size().reset_index(name="posts")
            fig.add_trace(go.Scatter(
                x=monthly["month"], y=monthly["posts"], name=name,
                mode="lines+markers", line=dict(color=PALETTE[i], width=2),
                marker=dict(size=8),
            ))
        apply_theme(fig, height=350, title="月別投稿数")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = go.Figure()
        for i, (name, df) in enumerate(datasets.items()):
            monthly = df.groupby("month")["likes"].mean().reset_index()
            fig.add_trace(go.Scatter(
                x=monthly["month"], y=monthly["likes"], name=name,
                mode="lines+markers", line=dict(color=PALETTE[i], width=2),
                marker=dict(size=8),
            ))
        apply_theme(fig, height=350, title="月別 平均いいね")
        st.plotly_chart(fig, use_container_width=True)

    # Engagement比較レーダー
    metrics = ["Avg Likes", "Avg RT", "Avg Replies", "Avg Eng Rate"]
    fig = go.Figure()
    for i, row in comp_df.iterrows():
        vals = [row[m] for m in metrics]
        fig.add_trace(go.Scatterpolar(
            r=vals, theta=metrics, fill="toself", name=row["Brand"],
            line_color=PALETTE[i], fillcolor=f"rgba({int(PALETTE[i][1:3],16)},{int(PALETTE[i][3:5],16)},{int(PALETTE[i][5:7],16)},0.2)",
        ))
    apply_theme(fig, height=400,
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
            angularaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
        ),
        title="エンゲージメント比較",
    )
    st.plotly_chart(fig, use_container_width=True)


# === Main ===
def main():
    # Header with inline SVG logo
    logo_svg = ""
    if LOGO_PATH.exists():
        logo_svg = LOGO_PATH.read_text()

    if logo_svg:
        import base64
        header_logo_b64 = base64.b64encode(logo_svg.encode()).decode()
        st.markdown(f"""
        <div class="main-header" style="display:flex;align-items:center;gap:16px;">
            <img src="data:image/svg+xml;base64,{header_logo_b64}" style="height: 50px;" />
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="main-header">
            <h1>X-Hack Analyzer</h1>
        </div>
        """, unsafe_allow_html=True)

    # Load datasets
    datasets = {}
    kadoraba_df = load_dataset("kadoraba", brand="kadoraba")
    if kadoraba_df is not None:
        datasets["カドラバ"] = kadoraba_df
    myca_df = load_dataset("myca", brand="dmm_myca")
    if myca_df is not None:
        datasets["DMM Myca"] = myca_df

    if not datasets:
        st.error("No data found. Run collection scripts first.")
        return

    analysis = load_analysis()

    # Sidebar
    if logo_svg:
        import base64
        logo_b64 = base64.b64encode(logo_svg.encode()).decode()
        st.sidebar.markdown(f"""
        <div style="text-align: center; padding: 1rem 0;">
            <img src="data:image/svg+xml;base64,{logo_b64}" style="width: 180px;" />
        </div>
        """, unsafe_allow_html=True)

    # Dataset selector
    dataset_name = st.sidebar.selectbox("Dataset", list(datasets.keys()))
    df = datasets[dataset_name]

    # Date filter
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Filters**")
    date_range = st.sidebar.date_input(
        "Period", value=(df["date"].min(), df["date"].max()),
        min_value=df["date"].min(), max_value=df["date"].max(),
    )
    if len(date_range) == 2:
        df = df[(df["date"] >= date_range[0]) & (df["date"] <= date_range[1])]

    authors = st.sidebar.multiselect("Authors", options=sorted(df["author"].unique()))
    if authors:
        df = df[df["author"].isin(authors)]

    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**{len(df):,}** posts | **{df['author'].nunique()}** authors")
    st.sidebar.markdown(f"{df['date'].min()} → {df['date'].max()}")

    # 算出根拠・定義
    with st.sidebar.expander("📐 指標の定義と算出根拠"):
        st.markdown("""
**データソース**
- twitter CLI（Cookie認証）でX検索APIからツイートを取得
- キーワード検索・ハッシュタグ検索・アカウント検索を併用し重複排除（tweet_id）

**基本指標**
- **いいね / RT / リプライ / 閲覧数**: X APIが返すtweet.metrics値をそのまま使用
- **投稿数**: 重複排除後のユニークtweet_id数
- **投稿者数**: ユニークauthor数（`nunique()`）

**エンゲージメント率（eng_rate）**
```
(likes + retweets + replies)
÷ max(views, 1) × 100
```
- 閲覧数0のツイートは分母を1にクリップ（ゼロ除算防止）
- 投稿単位で算出後、集計時は各投稿のeng_rateの**算術平均**を使用
- ※ 加重平均（合計エンゲージメント÷合計閲覧数）とは異なるため、少数閲覧・高eng率の投稿が平均を押し上げる可能性あり

**スパイク検出**
```
閾値 = 日別総エンゲージメントの平均 + 1σ（標準偏差）
```
- 1日の総エンゲージメント（likes+RT+replies合計）が閾値を超えた日をスパイクと判定

**施策分類ロジック**
- ツイート本文のキーワードマッチで26カテゴリに自動分類
- 優先順位: CL直前企画 > インタビュー > BOXプレゼント > デッキプレゼント > UGC企画 > 争奪戦 > その他
- 改行を除去してからマッチ（改行跨ぎのキーワード対応）
- 複数カテゴリに該当する場合は優先順位の高い方に分類

**公式 vs コミュニティ**
- 公式アカウント: カドラバ→`kadoraba`, `kadoraba_gundam` / Myca→`DMM_Myca`, `DMM_MycaMall`
- 上記以外をコミュニティ投稿として集計

**投稿タイプ分類（Overviewタブ）**
- キーワードリストによるOR検索（`str.contains`）
- 複数タイプに該当する投稿は重複カウントされる（排他分類ではない）
        """)
    with st.sidebar.expander("📁 データ収集方法"):
        st.markdown("""
**収集ツール**: `twitter` CLI（`~/.local/bin/twitter`）
**認証**: Cookie認証（`TWITTER_AUTH_TOKEN` + `TWITTER_CT0`）

**カドラバ**（`collect_kadoraba.py`）
- `カドラバ` キーワード検索（月別 since/until）
- `#カドラバ` ハッシュタグ検索
- `from:kadoraba` アカウント検索
- 各クエリ最大50件 → 重複排除

**DMM Myca**（`collect_myca.py`）
- `DMM Myca` / `DMMMyca` キーワード検索
- `#DMMMyca` ハッシュタグ検索
- `from:DMM_Myca` / `from:DMM_MycaMall` アカウント検索

**収集頻度**: `run_collect.sh` で手動 or cron（毎日9時・21時）
**保存形式**: CSV + JSON（`data/` ディレクトリ）
        """)

    # Official accounts config
    official_map = {
        "カドラバ": ["kadoraba", "kadoraba_gundam"],
        "DMM Myca": ["DMM_Myca", "DMM_MycaMall"],
    }
    official_accounts = official_map.get(dataset_name, [])

    # Tabs
    tab1, tab2, tab7, tab8, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Overview", "🔍 Engagement", "🔥 スパイク分析", "📋 施策分析", "👤 Authors", "🏢 Official", "⚔️ Compare", "🤖 AI Insights"
    ])

    with tab1:
        render_kpi_cards(df)
        render_timeline(df)
        col1, col2 = st.columns([2, 1])
        with col1:
            render_post_types(df)
        with col2:
            st.markdown(f'<div class="section-header">Activity Heatmap</div>', unsafe_allow_html=True)
            render_heatmap(df)

    with tab2:
        st.markdown(f'<div class="section-header">Engagement Breakdown</div>', unsafe_allow_html=True)
        render_engagement_breakdown(df)
        st.markdown(f'<div class="section-header">Top Posts</div>', unsafe_allow_html=True)
        render_top_tweets(df)

    with tab7:
        st.markdown(f'<div class="section-header">エンゲージメントスパイク分析</div>', unsafe_allow_html=True)
        st.caption("エンゲージメントが跳ねた日を自動検出し、どのツイートが効いたかをドリルダウンできます")
        render_spike_drilldown(df)

    with tab8:
        st.markdown(f'<div class="section-header">コンテンツ施策ディープ分析</div>', unsafe_allow_html=True)
        st.caption("BOX別・デッキ別・コラボ先別にどの施策が最も効果的かを可視化。施策を選ぶとツイートをドリルダウンできます")
        render_content_analysis(df)

    with tab3:
        st.markdown(f'<div class="section-header">Author Leaderboard</div>', unsafe_allow_html=True)
        render_authors(df)

    with tab4:
        st.markdown(f'<div class="section-header">Official Account Analysis</div>', unsafe_allow_html=True)
        render_official(df, official_accounts)

    with tab5:
        st.markdown(f'<div class="section-header">Brand Comparison</div>', unsafe_allow_html=True)
        render_comparison(datasets)

    with tab6:
        st.markdown(f'<div class="section-header">AI-Powered Insights</div>', unsafe_allow_html=True)
        render_ai_insights(analysis)


if __name__ == "__main__":
    main()

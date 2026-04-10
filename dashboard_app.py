import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="Clinical Coding Intelligence",
    page_icon="🏥",
    layout="wide"
)

# ── LOAD DATA ─────────────────────────────────────────────────
@st.cache_data(ttl=0)
def load_data():
    df = pd.read_excel("ehr_raw_data.xlsx", sheet_name="Raw Visit Data")
    df["Visit_Date"] = pd.to_datetime(df["Visit_Date"])

    CHRONIC = ["I10","E11.9","E78.5","E66.9","J44.1","E03.9",
               "I25.10","F32.1","F41.1","F33.0","F31.9","K21.0"]
    BH_DX   = ["F32.1","F41.1","F33.0","F43.10","F31.9",
               "F10.20","F40.10","F34.1","F43.22","F60.3"]
    EM_ORDER= ["99211","99212","99213","99214","99215"]
    EM_RATE = {"99211":24,"99212":55,"99213":92,"99214":136,"99215":193}

    def expected_cpt(m):
        if pd.isna(m): return None
        m = int(m)
        if m<=9:  return "99211"
        if m<=19: return "99212"
        if m<=29: return "99213"
        if m<=39: return "99214"
        return "99215"

    def flag(row):
        s,e = row["CPT_Code_Submitted"], row["Expected_CPT"]
        if s not in EM_ORDER: return "Non E&M"
        if e not in EM_ORDER: return "Unknown"
        si,ei = EM_ORDER.index(s), EM_ORDER.index(e)
        if si < ei: return "UNDERCODED"
        if si > ei: return "OVERCODED"
        return "CORRECT"

    def rev_gap(row):
        if row["Coding_Flag"] != "UNDERCODED": return 0.0
        return EM_RATE.get(row["Expected_CPT"],0) - EM_RATE.get(row["CPT_Code_Submitted"],0)

    def chronic_count(row):
        return sum(str(row.get(c,"")) in CHRONIC
                   for c in ["Primary_ICD10_Code","Secondary_ICD10_Code","Tertiary_ICD10_Code"])

    def has_bh_dx(row):
        return any(str(row.get(c,"")) in BH_DX
                   for c in ["Primary_ICD10_Code","Secondary_ICD10_Code","Tertiary_ICD10_Code"])

    pc = df[df["Service_Line"]=="Primary Care"].copy()
    pc["Expected_CPT"]  = pc["Visit_Duration_Min"].apply(expected_cpt)
    pc["Coding_Flag"]   = pc.apply(flag, axis=1)
    pc["Revenue_Gap"]   = pc.apply(rev_gap, axis=1)
    pc["Chronic_Count"] = pc.apply(chronic_count, axis=1)
    pc["Has_BH_Dx"]     = pc.apply(has_bh_dx, axis=1)
    pc["CCM_Missing"]   = (pc["Chronic_Count"]>=2) & (pc["CPT_Code_Submitted"]!="99490")
    pc["BHI_Missing"]   = pc["Has_BH_Dx"] & (pc["CPT_Code_Submitted"]!="99484")
    pc["G2211_Missing"] = (pc["CPT_Code_Submitted"].isin(["99212","99213","99214","99215"])) & \
                          (pc["Tertiary_ICD10_Code"].notna()) & \
                          (pc["Tertiary_ICD10_Code"].astype(str).str.strip().isin(["","nan"])==False)

    psych = df[df["Service_Line"]=="Psychiatry"].copy()
    psych["90833_Missing"] = (psych["Visit_Type"]=="Psychotherapy + Med Mgmt") & \
                              (psych["CPT_Code_Submitted"].isin(["99212","99213","99214","99215"]))

    return df, pc, psych

df, pc, psych = load_data()

# ── SIDEBAR ───────────────────────────────────────────────────
st.sidebar.image("https://img.shields.io/badge/Coding%20Intelligence-v1.0-blue", width=200)
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", [
    "Executive Summary",
    "Provider Analysis",
    "Add-on Code Gaps",
    "Visit Detail Queue",
])

st.sidebar.divider()
st.sidebar.markdown("**Filters**")
locations  = ["All"] + sorted(df["Location"].unique().tolist())
sel_loc    = st.sidebar.selectbox("Location", locations)
svc_lines  = ["All"] + sorted(df["Service_Line"].unique().tolist())
sel_svc    = st.sidebar.selectbox("Service line", svc_lines)
payers     = ["All"] + sorted(df["Payer"].dropna().unique().tolist())
sel_payer  = st.sidebar.selectbox("Payer", payers)

def apply_filters(data):
    d = data.copy()
    if sel_loc   != "All": d = d[d["Location"]==sel_loc]
    if sel_svc   != "All": d = d[d["Service_Line"]==sel_svc]
    if sel_payer != "All": d = d[d["Payer"]==sel_payer]
    return d

df_f  = apply_filters(df)
pc_f  = apply_filters(pc)
psych_f = apply_filters(psych)

# ── COMPUTED TOTALS ───────────────────────────────────────────
total_visits    = len(df_f)
undercoded      = (pc_f["Coding_Flag"]=="UNDERCODED").sum()
undercode_rate  = undercoded/len(pc_f)*100 if len(pc_f)>0 else 0
em_gap          = pc_f["Revenue_Gap"].sum()
ccm_gap         = pc_f["CCM_Missing"].sum() * 62
bhi_gap         = pc_f["BHI_Missing"].sum() * 45
g2211_gap       = pc_f["G2211_Missing"].sum() * 16
addon_90833_gap = psych_f["90833_Missing"].sum() * 65
total_addon_gap = ccm_gap + bhi_gap + g2211_gap + addon_90833_gap
total_gap       = em_gap + total_addon_gap


# ══════════════════════════════════════════════════════════════
# PAGE 1 — EXECUTIVE SUMMARY
# ══════════════════════════════════════════════════════════════
if page == "Executive Summary":
    st.title("Clinical Coding Intelligence")
    st.caption(f"Analyzing {total_visits:,} visits · Primary Care, Behavioral Health, Psychiatry")
    st.divider()

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total revenue gap",    f"${total_gap:,.0f}",  "Steps 3 + 4C")
    c2.metric("E&M undercode rate",   f"{undercode_rate:.1f}%", f"{undercoded} visits")
    c3.metric("Missing add-on codes", f"${total_addon_gap:,.0f}", "Unclaimed revenue")
    c4.metric("Visits analyzed",      f"{total_visits:,}",   "3 service lines")

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Revenue gap breakdown")
        fig = px.pie(
            values=[em_gap, total_addon_gap],
            names=["E&M undercoding", "Missing add-on codes"],
            color_discrete_sequence=["#E24B4A","#EF9F27"],
            hole=0.5,
        )
        fig.update_traces(textinfo="label+percent")
        fig.update_layout(showlegend=False, margin=dict(t=10,b=10,l=10,r=10), height=280)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Visits by service line")
        sl_counts = df_f["Service_Line"].value_counts().reset_index()
        sl_counts.columns = ["Service Line","Count"]
        fig2 = px.pie(sl_counts, values="Count", names="Service Line",
                      color_discrete_sequence=["#185FA5","#EF9F27","#1D9E75"], hole=0.5)
        fig2.update_traces(textinfo="label+value")
        fig2.update_layout(showlegend=False, margin=dict(t=10,b=10,l=10,r=10), height=280)
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Top CPT codes submitted")
    cpt_counts = df_f["CPT_Code_Submitted"].value_counts().head(10).reset_index()
    cpt_counts.columns = ["CPT Code","Count"]
    fig3 = px.bar(cpt_counts, x="CPT Code", y="Count",
                  color_discrete_sequence=["#185FA5"])
    fig3.update_layout(margin=dict(t=10,b=10), height=280)
    st.plotly_chart(fig3, use_container_width=True)

    st.subheader("Annual revenue gap projector")
    st.caption("Adjust your monthly visit volume to project the annual revenue gap")
    monthly_vol = st.slider("Monthly visits across all locations", 100, 3000, 500, step=50)
    proj_em     = monthly_vol * 0.304 * 50 * 12
    proj_addon  = monthly_vol * (total_addon_gap / max(total_visits,1)) * 12
    proj_total  = proj_em + proj_addon
    p1,p2,p3 = st.columns(3)
    p1.metric("Projected annual E&M gap",    f"${proj_em:,.0f}")
    p2.metric("Projected annual add-on gap", f"${proj_addon:,.0f}")
    p3.metric("Total projected annual gap",  f"${proj_total:,.0f}")


# ══════════════════════════════════════════════════════════════
# PAGE 2 — PROVIDER ANALYSIS
# ══════════════════════════════════════════════════════════════
elif page == "Provider Analysis":
    st.title("Provider Analysis")
    st.caption("Undercode rates and revenue gaps by provider — use for targeted education, not performance review")
    st.divider()

    prov = pc_f.groupby("Provider_Name").agg(
        Total_Visits     = ("Visit_ID",       "count"),
        Undercoded       = ("Coding_Flag",    lambda x: (x=="UNDERCODED").sum()),
        Revenue_Gap      = ("Revenue_Gap",    "sum"),
        Avg_Duration     = ("Visit_Duration_Min","mean"),
    ).reset_index()
    prov["Undercode_Rate_%"] = (prov["Undercoded"]/prov["Total_Visits"]*100).round(1)
    prov["Status"] = prov["Undercode_Rate_%"].apply(
        lambda r: "High risk" if r>40 else ("Medium risk" if r>20 else "Low risk"))

    sort_by = st.selectbox("Sort providers by",
        ["Revenue gap","Undercode rate","Total visits"])
    sort_map = {"Revenue gap":"Revenue_Gap","Undercode rate":"Undercode_Rate_%","Total visits":"Total_Visits"}
    prov = prov.sort_values(sort_map[sort_by], ascending=False)

    st.subheader("Undercode rate by provider")
    colors = prov["Undercode_Rate_%"].apply(
        lambda r: "#E24B4A" if r>40 else ("#EF9F27" if r>20 else "#1D9E75")).tolist()
    fig4 = go.Figure(go.Bar(
        x=prov["Undercode_Rate_%"], y=prov["Provider_Name"],
        orientation="h", marker_color=colors,
        text=prov["Undercode_Rate_%"].apply(lambda x: f"{x:.1f}%"),
        textposition="outside",
    ))
    fig4.add_vline(x=20, line_dash="dash", line_color="#1D9E75", annotation_text="20% threshold")
    fig4.add_vline(x=40, line_dash="dash", line_color="#E24B4A", annotation_text="40% threshold")
    fig4.update_layout(margin=dict(t=10,b=10,l=10,r=80),
                       height=max(300, len(prov)*45), xaxis_title="Undercode rate %")
    st.plotly_chart(fig4, use_container_width=True)

    st.subheader("Revenue gap by provider — E&M vs add-on codes")
    addon_by_prov = pc_f.groupby("Provider_Name").agg(
        CCM_Gap   = ("CCM_Missing",   lambda x: x.sum()*62),
        G2211_Gap = ("G2211_Missing", lambda x: x.sum()*16),
    ).reset_index()
    merged = prov.merge(addon_by_prov, on="Provider_Name", how="left").fillna(0)
    fig5 = go.Figure()
    fig5.add_trace(go.Bar(name="E&M gap", x=merged["Provider_Name"],
                          y=merged["Revenue_Gap"], marker_color="#E24B4A"))
    fig5.add_trace(go.Bar(name="Add-on gap",
                          x=merged["Provider_Name"],
                          y=merged["CCM_Gap"]+merged["G2211_Gap"],
                          marker_color="#EF9F27"))
    fig5.update_layout(barmode="stack", height=350,
                       margin=dict(t=10,b=10),
                       yaxis_title="Revenue gap ($)",
                       xaxis_tickangle=-30)
    st.plotly_chart(fig5, use_container_width=True)

    st.subheader("Provider scorecard")
    display_prov = prov[["Provider_Name","Total_Visits","Undercoded",
                          "Undercode_Rate_%","Revenue_Gap","Avg_Duration","Status"]].copy()
    display_prov["Revenue_Gap"]   = display_prov["Revenue_Gap"].apply(lambda x: f"${x:,.0f}")
    display_prov["Avg_Duration"]  = display_prov["Avg_Duration"].apply(lambda x: f"{x:.1f} min")
    display_prov["Undercode_Rate_%"] = display_prov["Undercode_Rate_%"].apply(lambda x: f"{x}%")
    display_prov.columns = ["Provider","Visits","Undercoded","Undercode Rate",
                             "Revenue Gap","Avg Duration","Status"]
    st.dataframe(display_prov, use_container_width=True, hide_index=True)

    st.info("Dr. Carlos Reyes has the lowest undercode rate — use him as the benchmark for provider education.")


# ══════════════════════════════════════════════════════════════
# PAGE 3 — ADD-ON CODE GAPS
# ══════════════════════════════════════════════════════════════
elif page == "Add-on Code Gaps":
    st.title("Add-on Code Gaps")
    st.caption("Revenue missed because qualifying add-on codes were never submitted")
    st.divider()

    ccm_count   = pc_f["CCM_Missing"].sum()
    bhi_count   = pc_f["BHI_Missing"].sum()
    g2211_count = pc_f["G2211_Missing"].sum()
    p90833_count= psych_f["90833_Missing"].sum()

    a1,a2,a3,a4 = st.columns(4)
    a1.metric("CCM (99490) gap",      f"${ccm_count*62:,.0f}",   f"{ccm_count} visits")
    a2.metric("90833 add-on gap",     f"${p90833_count*65:,.0f}",f"{p90833_count} visits")
    a3.metric("G2211 complex gap",    f"${g2211_count*16:,.0f}", f"{g2211_count} visits")
    a4.metric("Total add-on gap",     f"${total_addon_gap:,.0f}","All codes combined")

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Revenue by add-on code type")
        addon_df = pd.DataFrame({
            "Code": ["CCM (99490)","Psych add-on (90833)","Complex (G2211)","BHI (99484)"],
            "Revenue": [ccm_count*62, p90833_count*65, g2211_count*16, bhi_count*45]
        })
        fig6 = px.bar(addon_df, x="Code", y="Revenue",
                      color_discrete_sequence=["#E24B4A"],
                      text=addon_df["Revenue"].apply(lambda x: f"${x:,.0f}"))
        fig6.update_traces(textposition="outside")
        fig6.update_layout(height=300, margin=dict(t=10,b=10), yaxis_title="Gap ($)")
        st.plotly_chart(fig6, use_container_width=True)

    with col2:
        st.subheader("Missing add-ons by location")
        loc_addon = pc_f.groupby("Location").agg(
            CCM_Gap   = ("CCM_Missing",   lambda x: x.sum()*62),
            G2211_Gap = ("G2211_Missing", lambda x: x.sum()*16),
        ).reset_index()
        loc_addon["Total"] = loc_addon["CCM_Gap"] + loc_addon["G2211_Gap"]
        loc_addon = loc_addon.sort_values("Total")
        fig7 = px.bar(loc_addon, x="Total", y="Location",
                      orientation="h", color_discrete_sequence=["#185FA5"],
                      text=loc_addon["Total"].apply(lambda x: f"${x:,.0f}"))
        fig7.update_traces(textposition="outside")
        fig7.update_layout(height=300, margin=dict(t=10,b=10,r=60), xaxis_title="Gap ($)")
        st.plotly_chart(fig7, use_container_width=True)

    st.subheader("CCM monthly revenue calculator")
    st.caption("CCM is billed monthly per qualifying patient — this is recurring revenue")
    qualifying = st.slider("Number of qualifying patients (2+ chronic conditions)",
                           10, 500, int(ccm_count), step=1)
    m1, m2, m3 = st.columns(3)
    m1.metric("Monthly CCM revenue",  f"${qualifying*62:,.0f}")
    m2.metric("Annual CCM revenue",   f"${qualifying*62*12:,.0f}")
    m3.metric("3-year CCM revenue",   f"${qualifying*62*36:,.0f}")
    st.warning("CCM requires 20 minutes of documented care coordination per month per patient. "
               "Verify your team is logging this time before billing.")

    st.subheader("Missing add-ons by payer")
    payer_addon = pc_f.groupby("Payer").agg(
        CCM_Gap   = ("CCM_Missing",   lambda x: x.sum()*62),
        G2211_Gap = ("G2211_Missing", lambda x: x.sum()*16),
    ).reset_index()
    payer_addon["Total"] = payer_addon["CCM_Gap"] + payer_addon["G2211_Gap"]
    payer_addon = payer_addon.sort_values("Total", ascending=False)
    fig8 = px.bar(payer_addon, x="Payer", y="Total",
                  color_discrete_sequence=["#185FA5"],
                  text=payer_addon["Total"].apply(lambda x: f"${x:,.0f}"))
    fig8.update_traces(textposition="outside")
    fig8.update_layout(height=300, margin=dict(t=10,b=10), yaxis_title="Gap ($)")
    st.plotly_chart(fig8, use_container_width=True)
    st.warning("Self-Pay patients generally do not qualify for CCM or G2211. "
               "Review flagged self-pay visits before submitting claims.")


# ══════════════════════════════════════════════════════════════
# PAGE 4 — VISIT DETAIL QUEUE
# ══════════════════════════════════════════════════════════════
elif page == "Visit Detail Queue":
    st.title("Flagged Visit Queue")
    st.caption("Every visit flagged for coding review — filter and search to prioritize work")
    st.divider()

    flagged_em = pc_f[pc_f["Coding_Flag"]=="UNDERCODED"][[
        "Visit_ID","Visit_Date","Location","Provider_Name",
        "Visit_Type","CPT_Code_Submitted","Expected_CPT",
        "Visit_Duration_Min","Primary_Diagnosis","Payer","Revenue_Gap"
    ]].copy()
    flagged_em["Flag_Type"]   = "UNDERCODED"
    flagged_em["Revenue_Gap"] = flagged_em["Revenue_Gap"]
    flagged_em = flagged_em.rename(columns={"Expected_CPT":"Recommended_CPT"})

    flagged_ccm = pc_f[pc_f["CCM_Missing"]][[
        "Visit_ID","Visit_Date","Location","Provider_Name",
        "Visit_Type","CPT_Code_Submitted","Visit_Duration_Min",
        "Primary_Diagnosis","Payer"
    ]].copy()
    flagged_ccm["Recommended_CPT"] = "Add 99490"
    flagged_ccm["Flag_Type"]       = "MISSING CCM"
    flagged_ccm["Revenue_Gap"]     = 62

    flagged_psych = psych_f[psych_f["90833_Missing"]][[
        "Visit_ID","Visit_Date","Location","Provider_Name",
        "Visit_Type","CPT_Code_Submitted","Visit_Duration_Min",
        "Primary_Diagnosis","Payer"
    ]].copy()
    flagged_psych["Recommended_CPT"] = "Add 90833"
    flagged_psych["Flag_Type"]       = "MISSING 90833"
    flagged_psych["Revenue_Gap"]     = 65

    all_flagged = pd.concat([flagged_em, flagged_ccm, flagged_psych],
                            ignore_index=True).sort_values("Revenue_Gap", ascending=False)

    f1, f2, f3 = st.columns(3)
    with f1:
        flag_filter = st.selectbox("Filter by flag type",
            ["All","UNDERCODED","MISSING CCM","MISSING 90833"])
    with f2:
        prov_filter = st.selectbox("Filter by provider",
            ["All"] + sorted(all_flagged["Provider_Name"].unique().tolist()))
    with f3:
        min_gap = st.slider("Minimum revenue gap $", 0, 200, 0, step=10)

    filtered = all_flagged.copy()
    if flag_filter != "All":
        filtered = filtered[filtered["Flag_Type"]==flag_filter]
    if prov_filter != "All":
        filtered = filtered[filtered["Provider_Name"]==prov_filter]
    filtered = filtered[filtered["Revenue_Gap"] >= min_gap]

    st.caption(f"Showing {len(filtered):,} flagged visits · "
               f"Total gap: ${filtered['Revenue_Gap'].sum():,.0f}")

    display = filtered[[
        "Visit_ID","Visit_Date","Provider_Name","Location",
        "Visit_Type","CPT_Code_Submitted","Recommended_CPT",
        "Visit_Duration_Min","Revenue_Gap","Flag_Type","Payer"
    ]].copy()
    display["Visit_Date"]    = display["Visit_Date"].dt.strftime("%Y-%m-%d")
    display["Revenue_Gap"]   = display["Revenue_Gap"].apply(lambda x: f"${x:,.0f}")
    display.columns = ["Visit ID","Date","Provider","Location","Visit Type",
                       "Submitted CPT","Recommended CPT","Duration (min)",
                       "Revenue Gap","Flag","Payer"]

    st.dataframe(display, use_container_width=True, hide_index=True, height=500)

    st.divider()
    csv = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download flagged visits as CSV",
        data=csv,
        file_name="flagged_visits.csv",
        mime="text/csv",
    )

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_local_storage import LocalStorage

API_URL = "http://127.0.0.1:8000"
st.set_page_config(page_title="InsightFlow AI", page_icon="📊", layout="wide")
st.markdown(
    """
    <style>
    .stApp {
        background: #07152f;
    }

    [data-testid="stSidebar"] {
        background: #06122a;
        border-right: 1px solid #173a70;
    }

    [data-testid="stSidebar"] * {
        color: #e8f0ff;
    }

    .dashboard-title {
        font-size: 2.4rem;
        font-weight: 700;
        color: #f8fbff;
        margin-bottom: 0.2rem;
    }

    .dashboard-subtitle {
        color: #8ca6c9;
        font-size: 1rem;
        margin-bottom: 1.5rem;
    }

    .section-title {
        color: #f8fbff;
        font-size: 1.25rem;
        font-weight: 600;
        margin-top: 1rem;
        margin-bottom: 0.75rem;
    }

    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #0d2c5c, #0a1f43);
        border: 1px solid #164887;
        border-radius: 14px;
        padding: 1rem;
        min-height: 118px;
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.18);
    }

    div[data-testid="stMetricLabel"] {
        color: #9db7dc;
    }

    div[data-testid="stMetricValue"] {
        color: #ffffff;
    }

    div[data-testid="stMetricDelta"] {
        color: #38d996;
    }

    .welcome-card {
        background: linear-gradient(135deg, #123d79, #0b2550);
        border: 1px solid #1c5eaa;
        border-radius: 16px;
        padding: 1.4rem;
        min-height: 170px;
    }

    .welcome-card h2 {
        color: #ffffff;
        margin-bottom: 0.5rem;
    }

    .welcome-card p {
        color: #b9cbea;
        margin-bottom: 0;
    }

    .info-card {
        background: #0a2045;
        border: 1px solid #17457f;
        border-radius: 16px;
        padding: 1.2rem;
        min-height: 170px;
    }

    .info-card h3 {
        color: #ffffff;
        margin-bottom: 0.7rem;
    }

    .info-card p {
        color: #b9cbea;
        margin: 0.25rem 0;
    }

    .stButton > button {
        border-radius: 8px;
        border: 1px solid #256dcc;
        background: #0e4fa8;
        color: white;
    }

    .stButton > button:hover {
        border-color: #65a9ff;
        background: #1765c4;
        color: white;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


local_storage = LocalStorage()
HISTORY_KEY = "insightflow_upload_history"


def get_upload_history() -> list[dict]:
    stored_history = local_storage.getItem(HISTORY_KEY)

    if not stored_history:
        return []

    if isinstance(stored_history, list):
        return stored_history

    return []


def save_upload_history(upload_result: dict, project_id: int) -> None:
    history = get_upload_history()

    history.insert(
        0,
        {
            "filename": upload_result.get("filename", "Unknown file"),
            "dataset_id": upload_result.get("dataset_id"),
            "project_id": project_id,
            "quality_status": upload_result.get(
                "quality_status",
                "Processed",
            ),
        },
    )

    local_storage.setItem(HISTORY_KEY, history)


def clear_upload_history() -> None:
    local_storage.deleteItem(HISTORY_KEY)

def auth_headers():
    token = st.session_state.get("access_token")
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


@st.cache_data(ttl=30)
def api(endpoint: str):
    try:
        response = requests.get(
            f"{API_URL}{endpoint}",
            headers=auth_headers(),
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as error:
        if error.response is not None:
            try:
                detail = error.response.json().get(
                    "detail",
                    "API request failed.",
                )
            except ValueError:
                detail = "API request failed."

            st.error(detail)
        else:
            st.error(f"API request failed: {error}")

        return None


def api_write(
    method: str,
    endpoint: str,
    payload: dict | None = None,
):
    try:
        response = requests.request(
            method=method,
            url=f"{API_URL}{endpoint}",
            headers=auth_headers(),
            json=payload,
            timeout=15,
        )
        response.raise_for_status()

        if response.status_code == 204:
            return True

        return response.json()

    except requests.RequestException as error:
        if error.response is not None:
            try:
                detail = error.response.json().get(
                    "detail",
                    "Request failed.",
                )
            except ValueError:
                detail = "Request failed."

            st.error(detail)
        else:
            st.error(f"Request failed: {error}")

        return None

def upload_csv(uploaded_file):
    project_id = st.session_state["selected_project_id"]
    try:
        response = requests.post(
            f"{API_URL}/upload",
            headers=auth_headers(),
            data={"project_id": str(project_id)},
            files={
                "file": (
                    uploaded_file.name,
                    uploaded_file.getvalue(),
                    "text/csv",
                )
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as error:
        st.error(f"Upload failed: {error}")
        return None


def login(email: str, password: str) -> bool:
    if not email.strip():
        st.error("Email is required.")
        return False

    if not password:
        st.error("Password is required.")
        return False

    try:
        response = requests.post(
            f"{API_URL}/auth/login",
            json={
                "email": email.strip(),
                "password": password,
            },
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        if error.response is not None:
            try:
                detail = error.response.json().get(
                    "detail",
                    "Login failed.",
                )
            except ValueError:
                detail = "Login failed."

            st.error(f"Login failed: {detail}")
        else:
            st.error(f"Login failed: {error}")

        return False

    data = response.json()

    st.session_state["access_token"] = data["access_token"]
    st.session_state["current_user"] = data["user"]

    st.cache_data.clear()

    return True

def register(
    email: str,
    username: str,
    password: str,
    confirm_password: str,
) -> bool:
    if not email.strip():
        st.error("Email is required.")
        return False

    if not username.strip():
        st.error("Username is required.")
        return False

    if not password:
        st.error("Password is required.")
        return False

    if password != confirm_password:
        st.error("Passwords do not match.")
        return False

    if len(password) < 8:
        st.error("Password must contain at least 8 characters.")
        return False

    try:
        response = requests.post(
            f"{API_URL}/auth/register",
            json={
                "email": email.strip(),
                "username": username.strip(),
                "password": password,
                "role": "viewer",
            },
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        if error.response is not None:
            try:
                detail = error.response.json().get(
                    "detail",
                    "Registration failed.",
                )
            except ValueError:
                detail = "Registration failed."

            st.error(f"Registration failed: {detail}")
        else:
            st.error(f"Registration failed: {error}")

        return False

    st.success(
        "Account created successfully. "
        "Please sign in with your new account."
    )

    return True

    



def chart(items, title, x="name", y="count"):
    if items:
        st.plotly_chart(px.bar(pd.DataFrame(items), x=x, y=y, color=x, title=title), use_container_width=True)
    else:
        st.info("No data is available for this chart.")


def donut_chart(items, title):
    if not items:
        st.info("No data is available for this chart.")
        return

    values = pd.DataFrame(items)
    figure = px.pie(
        values,
        names="name",
        values="count",
        hole=0.55,
        title=title,
    )
    figure.update_layout(showlegend=True, margin=dict(t=55, l=10, r=10, b=10))
    st.plotly_chart(figure, use_container_width=True)


def quality_gauge(score):
    figure = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=float(score),
            number={"suffix": "/100"},
            title={"text": "Data Quality"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#2563eb"},
                "steps": [
                    {"range": [0, 60], "color": "#fee2e2"},
                    {"range": [60, 80], "color": "#fef3c7"},
                    {"range": [80, 100], "color": "#dcfce7"},
                ],
            },
        )
    )
    figure.update_layout(height=280, margin=dict(t=55, l=25, r=25, b=15))
    st.plotly_chart(figure, use_container_width=True)


def render_action(item, kind):
    level = item.get("severity" if kind == "insight" else "priority", "low").lower()
    message = (
        f"**{item.get('title', 'Insight')}**  \n{item.get('message', '')}"
        if kind == "insight"
        else (
            f"**{item.get('recommendation', 'Recommendation')}**  \n"
            f"{item.get('rationale', '')}"
        )
    )

    if level == "high":
        st.error(message)
    elif level == "medium":
        st.warning(message)
    else:
        st.info(message)


st.markdown(
    '<div class="dashboard-title">InsightFlow AI</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="dashboard-subtitle">'
    "Executive analytics and data quality workspace"
    "</div>",
    unsafe_allow_html=True,
)

if "access_token" not in st.session_state:
    st.subheader("Welcome to InsightFlow AI")

    auth_mode = st.radio(
        "Choose an option",
        ["Sign in", "Sign up"],
        horizontal=True,
    )

    if auth_mode == "Sign in":
        with st.form("login_form"):
            email = st.text_input(
                "Email",
                placeholder="you@example.com",
            )
            password = st.text_input(
                "Password",
                type="password",
            )
            submitted = st.form_submit_button("Sign in")

        if submitted and login(email, password):
            st.rerun()

    else:
        with st.form("signup_form"):
            username = st.text_input(
                "Username",
                placeholder="your username",
            )
            email = st.text_input(
                "Email",
                placeholder="you@example.com",
            )
            password = st.text_input(
                "Password",
                type="password",
            )
            confirm_password = st.text_input(
                "Confirm password",
                type="password",
            )
            submitted = st.form_submit_button("Create account")

        if submitted and register(
            email=email,
            username=username,
            password=password,
            confirm_password=confirm_password,
        ):
            st.rerun()

    st.stop()

current_user = st.session_state["current_user"]
st.sidebar.caption(
    f"Signed in as {current_user['username']} "
    f"({current_user['role']})"
)

if st.sidebar.button("Sign out"):
    st.session_state.pop("access_token", None)
    st.session_state.pop("current_user", None)
    st.session_state.pop("selected_project_id", None)
    st.cache_data.clear()
    st.rerun()

projects = api("/api/projects")
if projects is None:
    st.stop()

if not projects:
    st.info("No projects are available for this account.")
    st.stop()

project_ids = [project["id"] for project in projects]
selected_project_id = st.sidebar.selectbox(
    "Project",
    project_ids,
    index=(
        project_ids.index(st.session_state["selected_project_id"])
        if st.session_state.get("selected_project_id") in project_ids
        else 0
    ),
    format_func=lambda value: next(
        project["name"]
        for project in projects
        if project["id"] == value
    ),
)
st.session_state["selected_project_id"] = selected_project_id

if not api("/database-health"):
    st.stop()

st.sidebar.subheader("Data pipeline")

uploaded_file = st.sidebar.file_uploader(
    "Upload task CSV",
    type=["csv"],
)

if st.sidebar.button(
    "Process CSV",
    disabled=uploaded_file is None,
):
    upload_result = upload_csv(uploaded_file)

    if upload_result is not None:
        save_upload_history(
            upload_result=upload_result,
            project_id=selected_project_id,
        )

        st.sidebar.success(
            f"Processed {upload_result['filename']} "
            f"({upload_result['quality_status']})."
        )

        st.cache_data.clear()
        st.rerun()

if st.sidebar.button("Refresh data"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.subheader("Upload history")

upload_history = get_upload_history()

if not upload_history:
    st.sidebar.caption("No uploads saved in this browser.")
else:
    for item in upload_history[:10]:
        filename = item.get("filename", "Unknown file")
        status = item.get("quality_status", "Processed")

        st.sidebar.write(f"**{filename}**")
        st.sidebar.caption(status)

    if st.sidebar.button("Clear browser history"):
        clear_upload_history()
        st.rerun()    


    

datasets = api("/api/datasets")
if not datasets:
    st.info("No stored datasets found. Upload a CSV through the pipeline first.")
    st.stop()

catalog = pd.DataFrame(datasets)
selected_id = st.sidebar.selectbox(
    "Analyze dataset", catalog["id"].tolist(),
    format_func=lambda value: f"{catalog.loc[catalog['id'] == value, 'filename'].iloc[0]} (ID {value})",
)
page = st.sidebar.radio(
    "Workspace",
    [
        "Executive Dashboard",
        "Dataset Profile",
        "Data Quality",
        "Statistics",
        "KPIs",
        "Trends",
        "Insights",
        "Recommendations",
        "Member Management",
    ],
)
if page == "Executive Dashboard":
    dataset = catalog.loc[
        catalog["id"] == selected_id
    ].iloc[0]

    kpis = api(f"/analytics/kpis/{selected_id}")
    quality = api(f"/analytics/quality/{selected_id}")
    trends = api(f"/analytics/trends/{selected_id}")
    insights = api(f"/analytics/insights/{selected_id}")
    recommendations = api(
        f"/analytics/recommendations/{selected_id}"
    )

    st.markdown(
        '<div class="section-title">Overview</div>',
        unsafe_allow_html=True,
    )

    st.caption(
        f"Selected dataset: {dataset['filename']}  |  "
        f"Dataset ID: {selected_id}"
    )

    if kpis:
        metric_one, metric_two, metric_three, metric_four = st.columns(4)

        metric_one.metric(
            "Total Tasks",
            f"{kpis.get('total_tasks', 0):,}",
        )

        metric_two.metric(
            "Completion Rate",
            f"{kpis.get('completion_rate', 0):.1f}%",
            f"{kpis.get('completed_tasks', 0):,} completed",
        )

        metric_three.metric(
            "Pending Tasks",
            f"{kpis.get('pending_tasks', 0):,}",
            f"{kpis.get('pending_rate', 0):.1f}% of total",
            delta_color="inverse",
        )

        metric_four.metric(
            "Estimated Hours",
            f"{kpis.get('total_estimated_hours', 0):,.1f}",
        )

    st.write("")

    welcome_column, quality_column = st.columns([1.35, 1])

    with welcome_column:
        username = current_user.get("username", "User")

        st.markdown(
            f"""
            <div class="welcome-card">
                <h2>Welcome back, {username}</h2>
                <p>
                    Monitor your project data, quality, workload,
                    and analytics from one workspace.
                </p>
                <p>
                    Current dataset: <strong>{dataset['filename']}</strong>
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with quality_column:
        quality_score = 0
        quality_grade = "N/A"
        quarantine_rate = 0

        if quality:
            quality_score = quality.get("quality_score", 0)
            quality_grade = quality.get("grade", "N/A")
            quality_metrics = quality.get("metrics", {})
            quarantine_rate = quality_metrics.get(
                "quarantine_rate",
                0,
            )

        st.markdown(
            f"""
            <div class="info-card">
                <h3>Data Quality</h3>
                <p><strong>Score:</strong> {quality_score:.1f}/100</p>
                <p><strong>Grade:</strong> {quality_grade}</p>
                <p><strong>Quarantine rate:</strong> {quarantine_rate:.1f}%</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")

    chart_column, status_column = st.columns([1.4, 1])

    with chart_column:
        st.markdown(
            '<div class="section-title">Workload overview</div>',
            unsafe_allow_html=True,
        )

        if kpis:
            chart(
                kpis.get(
                    "layer_workload_distribution",
                    [],
                ),
                "Estimated Workload by Layer",
                y="estimated_hours",
            )
        else:
            st.info("Workload data is not available.")

    with status_column:
        st.markdown(
            '<div class="section-title">Task status</div>',
            unsafe_allow_html=True,
        )

        if kpis:
            completion_data = [
                {
                    "name": "Completed",
                    "count": kpis.get(
                        "completed_tasks",
                        0,
                    ),
                },
                {
                    "name": "Pending",
                    "count": kpis.get(
                        "pending_tasks",
                        0,
                    ),
                },
            ]

            donut_chart(
                completion_data,
                "Delivery Status",
            )
        else:
            st.info("Task status data is not available.")

    st.write("")

    insight_column, recommendation_column = st.columns(2)

    with insight_column:
        st.markdown(
            '<div class="section-title">Key insights</div>',
            unsafe_allow_html=True,
        )

        insight_items = (
            insights.get("insights", [])
            if insights
            else []
        )

        if insight_items:
            for item in insight_items[:3]:
                render_action(item, "insight")
        else:
            st.success("No immediate risks were detected.")

    with recommendation_column:
        st.markdown(
            '<div class="section-title">Recommended actions</div>',
            unsafe_allow_html=True,
        )

        recommendation_items = (
            recommendations.get("recommendations", [])
            if recommendations
            else []
        )

        if recommendation_items:
            for item in recommendation_items[:3]:
                render_action(
                    item,
                    "recommendation",
                )
        else:
            st.success("No recommendations are pending.")
elif page == "Dataset Profile":
    data = api(f"/profiles/{selected_id}")
    if data:
        st.subheader(f"Dataset Profile: {data['filename']}")
        a, b = st.columns(2); a.metric("Rows", data["summary"]["rows"]); b.metric("Columns", data["summary"]["columns"])
        st.dataframe(pd.DataFrame(data["columns"]), use_container_width=True, hide_index=True)
        chart([{"column": key, "missing_count": value} for key, value in data["missing_value_analysis"].items()], "Missing Values by Column", x="column", y="missing_count")

elif page == "Statistics":
    data = api(f"/analytics/statistics/{selected_id}")
    if data:
        stats = pd.DataFrame(data["numeric_statistics"]).T.reset_index(names="column")
        if stats.empty: st.info("The selected dataset has no numeric columns.")
        else:
            st.dataframe(stats, use_container_width=True, hide_index=True)
            correlation = pd.DataFrame(data["correlation_matrix"])
            if not correlation.empty:
                figure = go.Figure(data=go.Heatmap(z=correlation.values, x=correlation.columns, y=correlation.index, colorscale="Blues", zmin=-1, zmax=1))
                figure.update_layout(title="Correlation Matrix"); st.plotly_chart(figure, use_container_width=True)
            st.subheader("Outlier Summary")
            st.dataframe(pd.DataFrame(data["outlier_summary"]).T.reset_index(names="column"), use_container_width=True, hide_index=True)

elif page == "Data Quality":
    data = api(
        f"/analytics/quality/{selected_id}"
    )

    if data:
        st.subheader("Data Quality Score")

        score = data.get(
            "quality_score",
            0,
        )

        grade = data.get(
            "grade",
            "N/A",
        )

        metrics = data.get(
            "metrics",
            {},
        )

        summary = data.get(
            "summary",
            {},
        )

        score_column, grade_column = st.columns(2)

        score_column.metric(
            "Overall Quality Score",
            f"{score:.1f}/100",
        )

        grade_column.metric(
            "Quality Grade",
            grade,
        )

        st.subheader("Quality Metrics")

        metric_1, metric_2, metric_3, metric_4 = st.columns(4)

        metric_1.metric(
            "Completeness",
            f"{metrics.get('completeness_score', 0):.1f}%",
        )

        metric_2.metric(
            "Uniqueness",
            f"{metrics.get('uniqueness_score', 0):.1f}%",
        )

        metric_3.metric(
            "Validity",
            f"{metrics.get('validity_score', 0):.1f}%",
        )

        metric_4.metric(
            "Readiness",
            f"{metrics.get('readiness_score', 0):.1f}%",
        )

        st.subheader("Dataset Quality Summary")

        summary_dataframe = pd.DataFrame(
            [
                {
                    "Metric": "Original Rows",
                    "Value": summary.get(
                        "original_rows",
                        0,
                    ),
                },
                {
                    "Metric": "Ready Rows",
                    "Value": summary.get(
                        "ready_rows",
                        0,
                    ),
                },
                {
                    "Metric": "Quarantined Rows",
                    "Value": summary.get(
                        "quarantined_rows",
                        0,
                    ),
                },
                {
                    "Metric": "Missing Values",
                    "Value": summary.get(
                        "missing_value_count",
                        0,
                    ),
                },
                {
                    "Metric": "Duplicate Rows",
                    "Value": summary.get(
                        "duplicate_row_count",
                        0,
                    ),
                },
                {
                    "Metric": "Duplicate Task IDs",
                    "Value": summary.get(
                        "duplicate_task_id_count",
                        0,
                    ),
                },
            ]
        )

        st.dataframe(
            summary_dataframe,
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Quality Issues")

        issues = data.get(
            "issues",
            [],
        )

        if not issues:
            st.success(
                "No quality issues were detected."
            )
        else:
            issues_dataframe = pd.DataFrame(
                issues
            )

            st.dataframe(
                issues_dataframe,
                use_container_width=True,
                hide_index=True,
            )

        st.metric(
            "Quarantine Rate",
            f"{metrics.get('quarantine_rate', 0):.1f}%",
        )

elif page == "KPIs":
    data = api(f"/analytics/kpis/{selected_id}")
    if data:
        a, b, c, d = st.columns(4)
        a.metric("Total Tasks", data["total_tasks"]); b.metric("Completed", data["completed_tasks"], f"{data['completion_rate']:.1f}%")
        c.metric("Pending", data["pending_tasks"], f"{data['pending_rate']:.1f}%"); d.metric("High-Priority Pending", data["high_priority_pending_tasks"])
        chart(data["layer_workload_distribution"], "Layer Workload Distribution", y="estimated_hours")
        chart(data["component_distribution"], "Component Distribution")

elif page == "Trends":
    data = api(f"/analytics/trends/{selected_id}")
    if data:
        left, right = st.columns(2)
        with left: chart(data["status_trends"], "Status Trend")
        with right: chart(data["priority_trends"], "Priority Trend")
        chart(data["layer_trends"], "Layer Trend")
        if data["time_trends"]:
            grain = st.selectbox("Time grain", list(data["time_trends"]))
            values = pd.DataFrame(data["time_trends"][grain])
            st.plotly_chart(px.line(values, x="period", y="count", markers=True, title=f"{grain.title()} Trend"), use_container_width=True)
        else: st.info("No date/time column was found for time-based trend analysis.")

elif page == "Insights":
    data = api(f"/analytics/insights/{selected_id}")
    if data:
        for item in data["insights"]:
            getattr(st, "error" if item["severity"] == "high" else "warning")(f"{item['title']}: {item['message']}")
        if not data["insights"]: st.info("No rule-based insights were generated.")

elif page == "Recommendations":
    data = api(f"/analytics/recommendations/{selected_id}")
    if data:
        for item in data["recommendations"]:
            st.markdown(f"**{item['priority'].title()} priority — {item['recommendation']}**  \n{item['rationale']}")
        if not data["recommendations"]: st.info("No recommendations were generated.")

elif page == "Member Management":
        st.subheader("Project Member Management")
    
        st.caption(
            "Manage users who can access the selected project."
        )
    
        project_name = next(
            (
                project["name"]
                for project in projects
                if project["id"] == selected_project_id
            ),
            f"Project {selected_project_id}",
        )
    
        st.markdown(
            f"### {project_name}"
        )
    
        members_endpoint = (
            f"/api/permissions/projects/"
            f"{selected_project_id}/members"
        )
    
        members = api(members_endpoint)
    
        if members is None:
            st.warning(
                "Only the project owner can manage members, "
                "or the member list could not be loaded."
            )
        else:
            st.markdown("#### Current members")
    
            if not members:
                st.info(
                    "This project does not have any additional members."
                )
            else:
                for member in members:
                    member_id = member["user_id"]
                    member_role = member["role"]
    
                    member_column, role_column, action_column = st.columns(
                        [2, 1.5, 1]
                    )
    
                    member_column.write(
                        f"User ID: `{member_id}`"
                    )
    
                    with role_column:
                        updated_role = st.selectbox(
                            "Role",
                            [
                                "viewer",
                                "analyst",
                                "editor",
                                "owner",
                            ],
                            index=[
                                "viewer",
                                "analyst",
                                "editor",
                                "owner",
                            ].index(member_role),
                            key=f"role_{selected_project_id}_{member_id}",
                            label_visibility="collapsed",
                        )
    
                    with action_column:
                        if st.button(
                            "Update",
                            key=f"update_{selected_project_id}_{member_id}",
                        ):
                            result = api_write(
                                method="PATCH",
                                endpoint=(
                                    f"{members_endpoint}/{member_id}"
                                ),
                                payload={
                                    "role": updated_role,
                                },
                            )
    
                            if result is not None:
                                st.success(
                                    f"User {member_id} role updated."
                                )
                                st.cache_data.clear()
                                st.rerun()
    
                        if st.button(
                            "Remove",
                            key=f"remove_{selected_project_id}_{member_id}",
                        ):
                            result = api_write(
                                method="DELETE",
                                endpoint=(
                                    f"{members_endpoint}/{member_id}"
                                ),
                            )
    
                            if result is not None:
                                st.success(
                                    f"User {member_id} removed."
                                )
                                st.cache_data.clear()
                                st.rerun()
    
            st.divider()
    
            st.markdown("#### Add a project member")
    
            with st.form(
                f"add_member_form_{selected_project_id}"
            ):
                user_id = st.number_input(
                    "User ID",
                    min_value=1,
                    step=1,
                    value=1,
                )
    
                role = st.selectbox(
                    "Project role",
                    [
                        "viewer",
                        "analyst",
                        "editor",
                        "owner",
                    ],
                )
    
                add_member_submitted = st.form_submit_button(
                    "Add member"
                )
    
            if add_member_submitted:
                result = api_write(
                    method="POST",
                    endpoint=members_endpoint,
                    payload={
                        "user_id": int(user_id),
                        "role": role,
                    },
                )
    
                if result is not None:
                    st.success(
                        f"User {int(user_id)} added as {role}."
                    )
                    st.cache_data.clear()
                    st.rerun()    

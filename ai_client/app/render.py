"""
Rendering functions for Streamlit UI components
"""
import json
import uuid
import pandas as pd
import streamlit as st
import plotly.graph_objects as go


def _render_download_buttons(fig: go.Figure, title: str, data: dict):
    """Render PNG and CSV download buttons for a chart"""
    col1, col2 = st.columns(2)
    unique_id = uuid.uuid4()
    with col1:
        try:
            img_bytes = fig.to_image(format="png", scale=2)
            st.download_button(
                "📥 PNG",
                data=img_bytes,
                file_name=f"{title.replace(' ', '_')}.png",
                mime="image/png",
                key=f"png_download_{unique_id}"
            )
        except Exception:
            pass

    with col2:
        try:
            if "x" in data and "y" in data:
                df = pd.DataFrame({"x": data["x"], "y": data["y"]})
            elif "labels" in data and "values" in data:
                df = pd.DataFrame({"label": data["labels"], "value": data["values"]})
            elif "values" in data:
                df = pd.DataFrame({"value": data["values"]})
            elif "series" in data:
                df_dict = {"x": data.get("x", [])}
                for s in data["series"]:
                    df_dict[s.get("name", "series")] = s.get("values", [])
                df = pd.DataFrame(df_dict)
            else:
                df = pd.DataFrame(data)
            st.download_button(
                "📥 CSV",
                data=df.to_csv(index=False),
                file_name=f"{title.replace(' ', '_')}.csv",
                mime="text/csv",
                key=f"chart_csv_download_{unique_id}"
            )
        except Exception:
            pass


def _render_statistics(stats: dict):
    """Render statistics expander"""
    with st.expander("📊 Statistics"):
        for key, value in stats.items():
            label = key.replace('_', ' ').title()
            if isinstance(value, float):
                st.write(f"**{label}**: {value:.4f}")
            elif isinstance(value, int):
                st.write(f"**{label}**: {value:,}")
            else:
                st.write(f"**{label}**: {value}")


def render_plotly_chart(chart_data: dict):
    """Render a Plotly chart from chart data JSON"""
    chart_type = chart_data.get("chart_type", "bar")
    title = chart_data.get("title", "")
    data = chart_data.get("data", {})
    layout_config = chart_data.get("layout", {})

    fig = None

    try:
        if chart_type == "bar":
            fig = go.Figure(go.Bar(
                x=data.get("x", []),
                y=data.get("y", []),
                marker_color=layout_config.get("color", "steelblue")
            ))
            if layout_config.get("yaxis_type") == "log":
                fig.update_yaxes(type="log")

        elif chart_type == "bar_horizontal":
            fig = go.Figure(go.Bar(
                x=data.get("x", []),
                y=data.get("y", []),
                orientation='h',
                marker_color=layout_config.get("color", "steelblue")
            ))

        elif chart_type == "bar_stacked":
            fig = go.Figure()
            for series in data.get("series", []):
                fig.add_trace(go.Bar(
                    name=series.get("name", ""),
                    x=data.get("x", []),
                    y=series.get("values", []),
                    marker_color=series.get("color")
                ))
            fig.update_layout(barmode='stack')

        elif chart_type == "bar_grouped":
            fig = go.Figure()
            for series in data.get("series", []):
                fig.add_trace(go.Bar(
                    name=series.get("name", ""),
                    x=data.get("x", []),
                    y=series.get("values", []),
                    marker_color=series.get("color")
                ))
            fig.update_layout(barmode='group')

        elif chart_type == "bar_categorical":
            categories = data.get("categories", [])
            y_labels = data.get("y", [])
            colors = data.get("colors", [])
            fig = go.Figure(go.Bar(
                y=y_labels,
                x=[1] * len(y_labels),
                orientation='h',
                marker_color=colors,
                text=categories,
                textposition='inside'
            ))
            fig.update_xaxes(showticklabels=False)

        elif chart_type == "pie":
            fig = go.Figure(go.Pie(
                labels=data.get("labels", []),
                values=data.get("values", []),
                marker_colors=data.get("colors") if data.get("colors") else None
            ))

        elif chart_type == "histogram":
            fig = go.Figure(go.Histogram(
                x=data.get("values", []),
                nbinsx=layout_config.get("nbins", 30),
                marker_color=layout_config.get("color", "steelblue")
            ))
            vline = layout_config.get("vline")
            if vline:
                fig.add_vline(
                    x=vline.get("x"),
                    line_color=vline.get("color", "red"),
                    line_dash="dash",
                    annotation_text=vline.get("label", "")
                )

        elif chart_type == "line":
            fig = go.Figure(go.Scatter(
                x=data.get("x", []),
                y=data.get("y", []),
                mode='lines',
                line=dict(color=layout_config.get("color", "blue"), width=2)
            ))

        elif chart_type == "line_multi":
            fig = go.Figure()
            for series in data.get("series", []):
                fig.add_trace(go.Scatter(
                    x=data.get("x", []),
                    y=series.get("values", []),
                    mode='lines',
                    name=series.get("name", ""),
                    line=dict(color=series.get("color"), width=2)
                ))

        elif chart_type == "line_step":
            fig = go.Figure(go.Scatter(
                x=data.get("x", []),
                y=data.get("y", []),
                mode='lines',
                line=dict(color=layout_config.get("color", "steelblue"), width=2, shape='hv')
            ))

        elif chart_type == "heatmap":
            fig = go.Figure(go.Heatmap(
                z=data.get("z", []),
                x=data.get("x", []),
                y=data.get("y", []),
                colorscale=layout_config.get("colorscale", "YlOrRd")
            ))

        else:
            st.warning(f"Unknown chart type: {chart_type}")
            return

        if fig:
            labels = data.get("labels", {})
            # labels can be a list (for pie charts) or dict (for axis labels)
            if isinstance(labels, dict):
                fig.update_layout(
                    title=title,
                    xaxis_title=labels.get("x", ""),
                    yaxis_title=labels.get("y", ""),
                    template="plotly_white"
                )
            else:
                fig.update_layout(title=title, template="plotly_white")

            vlines = layout_config.get("vlines", [])
            for vline in vlines:
                fig.add_vline(
                    x=vline.get("x"),
                    line_color=vline.get("color", "red"),
                    line_dash="dash",
                    annotation_text=vline.get("label", "")
                )

            st.plotly_chart(fig, use_container_width=True, key=f"plotly_{uuid.uuid4()}")
            _render_download_buttons(fig, title, data)

            stats = data.get("stats")
            if stats:
                _render_statistics(stats)

    except Exception as e:
        st.error(f"Error rendering chart: {str(e)}")
        st.text(chart_data)


def render_table(table_data: dict):
    """Render a table from structured table data JSON"""
    title = table_data.get("title", "")
    columns = table_data.get("columns", [])
    rows = table_data.get("rows", [])
    summary = table_data.get("summary", "")

    if not rows:
        st.info("No data to display")
        return

    df = pd.DataFrame(rows)

    if columns:
        valid_columns = [c for c in columns if c in df.columns]
        if valid_columns:
            df = df[valid_columns]

    if title:
        st.markdown(f"**{title}**")
    if summary:
        st.caption(summary)

    st.dataframe(df, use_container_width=True, hide_index=True, key=f"dataframe_{uuid.uuid4()}")

    st.download_button(
        "📥 CSV",
        data=df.to_csv(index=False),
        file_name=f"{title.replace(' ', '_')}.csv" if title else "data.csv",
        mime="text/csv",
        key=f"csv_download_{uuid.uuid4()}"
    )


def render_tool_request(name: str, arguments: dict):
    """Render tool call request (arguments only)"""
    with st.expander(f"Request Tool Call from MCP Server: {name}", expanded=False):
        st.json(arguments, key=f"json_request_{uuid.uuid4()}")


def render_tool_response(name: str, result: str, result_type: str | None, parsed_data: dict | None):
    """Render tool response (result only)"""
    if result_type == "chart" and parsed_data:
        with st.expander(f"Result: {name}", expanded=True):
            render_plotly_chart(parsed_data)
    elif result_type == "table" and parsed_data:
        with st.expander(f"Result: {name}", expanded=True):
            render_table(parsed_data)
    else:
        with st.expander(f"Result: {name}", expanded=True):
            try:
                parsed = json.loads(result)
                st.json(parsed, key=f"json_response_{uuid.uuid4()}")
            except json.JSONDecodeError:
                st.code(result, language="text", key=f"code_{uuid.uuid4()}")


def render_tool_call(name: str, arguments: dict, result: str, result_type: str | None, parsed_data: dict | None):
    """Render a complete tool call (for history display)"""
    render_tool_request(name, arguments)
    render_tool_response(name, result, result_type, parsed_data)

import pandas as pd
import plotly.express as px

from constants import STATUS_COLORS


def make_well_map(filtered_df):
    mappable = filtered_df.dropna(subset=["latitude", "longitude"]).copy()
    oil = pd.to_numeric(mappable["OIL"], errors="coerce").fillna(0).clip(lower=0)
    if not mappable.empty and oil.max() > 0:
        # Keep every well visible while making higher oil production clearly larger.
        mappable["marker_size"] = 7 + (oil / oil.max() * 23)
    else:
        mappable["marker_size"] = 7

    fig = px.scatter_map(
        mappable,
        lat="latitude",
        lon="longitude",
        color="status",
        color_discrete_map=STATUS_COLORS,
        size="marker_size",
        size_max=30,
        hover_name="ALIAS",
        hover_data={
            "field": True,
            "OIL": True,
            "water_cut_pct": True,
            "latitude": False,
            "longitude": False,
        },
        text="ALIAS",
        map_style="open-street-map",
    )
    fig.update_traces(textposition="top center", textfont=dict(color="white", size=11))
    fig.update_layout(
        height=420,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="#0b1220",
        legend=dict(
            x=0.01,
            y=0.99,
            xanchor="left",
            yanchor="top",
            bgcolor="rgba(20,29,46,0.82)",
            bordercolor="rgba(148,163,184,0.45)",
            borderwidth=1,
            font=dict(color="#e2e8f0", size=11),
        ),
        map=dict(
            style="white-bg",
            layers=[
                {
                    "below": "traces",
                    "sourcetype": "raster",
                    "sourceattribution": "Esri, Maxar, Earthstar Geographics",
                    "source": [
                        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                    ],
                }
            ],
        ),
    )
    if not mappable.empty:
        fig.update_maps(
            bounds=dict(
                west=mappable["longitude"].min() - 0.01,
                east=mappable["longitude"].max() + 0.01,
                south=mappable["latitude"].min() - 0.01,
                north=mappable["latitude"].max() + 0.01,
            )
        )
    return fig

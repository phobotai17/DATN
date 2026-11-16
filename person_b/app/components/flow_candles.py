"""Candlesticks for traffic counts sampled at equal time intervals."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go


def video_time(seconds):
    minutes, seconds = divmod(max(0, int(seconds)), 60)
    return f'{minutes}:{seconds:02d}'


def flow_candles(counts, samples_per_candle, *, elapsed_axis=False):
    """One candle per complete group of evenly spaced count samples."""
    groups = len(counts) // samples_per_candle
    complete = counts.iloc[:groups * samples_per_candle]
    values = complete.to_numpy().reshape(groups, samples_per_candle)
    starts = complete.index[::samples_per_candle]
    valid = ~pd.isna(values).any(axis=1)
    starts, values = starts[valid], values[valid]
    figure = go.Figure(go.Candlestick(
        x=[video_time(t) for t in starts] if elapsed_axis else starts,
        open=values[:, 0], high=values.max(axis=1), low=values.min(axis=1),
        close=values[:, -1], name='Lưu lượng đã ghi',
        increasing_line_color='#16836d', decreasing_line_color='#bb5538',
    ))
    figure.update_layout(xaxis_rangeslider_visible=False,
                         xaxis_title='Thời gian video' if elapsed_axis else 'Thời gian ghi')
    if elapsed_axis:
        figure.update_xaxes(type='category', nticks=12)
    return figure


def counts_by_elapsed(events, covered_seconds, sample_seconds):
    """Count events in complete samples, including observed samples with no events."""
    n = int(covered_seconds // sample_seconds)
    counts = np.zeros(n, dtype=int)
    for event in events:
        index = int(event['time_s'] // sample_seconds)
        if 0 <= index < n:
            counts[index] += 1
    return pd.Series(counts, index=np.arange(n) * sample_seconds)

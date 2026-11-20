"""
forecasting.py
==============
Module dự báo lưu lượng chuỗi thời gian (Member B, Week 3 - FR5, RQ4).
Hỗ trợ:
  1. Các mô hình cơ sở (Baselines):
     - Persistence (Last observed value)
     - Seasonal Naive (Lấy lại giá trị chu kỳ trước)
     - Moving Average
  2. Các mô hình học sâu (Deep Learning):
     - LSTM (Long Short-Term Memory)
     - GRU (Gated Recurrent Unit)
  3. Đánh giá sai số đa chỉ số: MAE, RMSE, MAPE
"""

from typing import Dict, List, Tuple, Union, Optional
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset


def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """Tính toán MAE, RMSE, MAPE cho kết quả dự báo."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))

    # Tránh chia cho 0 khi tính MAPE
    non_zero = y_true != 0
    if np.any(non_zero):
        mape = float(np.mean(np.abs((y_true[non_zero] - y_pred[non_zero]) / y_true[non_zero])) * 100)
    else:
        mape = 0.0

    return {
        "MAE": round(mae, 3),
        "RMSE": round(rmse, 3),
        "MAPE": round(mape, 2),
    }


# ------------------------------------------------------------- Baselines --
class BaselineForecaster:
    @staticmethod
    def persistence(history: np.ndarray, horizon: int = 3) -> np.ndarray:
        """Persistence: Dự báo giá trị tương lai bằng giá trị quan sát cuối cùng."""
        last_val = history[-1]
        return np.full((horizon,), last_val)

    @staticmethod
    def seasonal_naive(history: np.ndarray, season_length: int = 12, horizon: int = 3) -> np.ndarray:
        """
        Seasonal Naive: Lấy giá trị của đúng thời điểm đó ở chu kỳ trước (season_length).
        Ví dụ bước 5 phút -> 1 giờ = 12 bước, 24 giờ = 288 bước.
        """
        if len(history) < season_length:
            return BaselineForecaster.persistence(history, horizon)
        
        preds = []
        for h in range(horizon):
            idx = -season_length + (h % season_length)
            preds.append(history[idx])
        return np.array(preds)

    @staticmethod
    def moving_average(history: np.ndarray, window: int = 6, horizon: int = 3) -> np.ndarray:
        """Dự báo bằng giá trị trung bình trượt của window bước gần nhất."""
        mean_val = np.mean(history[-window:])
        return np.full((horizon,), mean_val)


# --------------------------------------------------------- Deep Learning --
class TrafficRNN(nn.Module):
    def __init__(
        self,
        cell_type: str = "LSTM",
        input_dim: int = 1,
        hidden_dim: int = 64,
        num_layers: int = 2,
        output_dim: int = 3,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.cell_type = cell_type.upper()
        if self.cell_type == "GRU":
            self.rnn = nn.GRU(input_dim, hidden_dim, num_layers=num_layers, batch_first=True, dropout=dropout)
        else:
            self.rnn = nn.LSTM(input_dim, hidden_dim, num_layers=num_layers, batch_first=True, dropout=dropout)

        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Linear(32, output_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.rnn(x)
        # Lấy hidden state của bước thời gian cuối cùng
        last_hidden = out[:, -1, :]
        preds = self.fc(last_hidden)
        return preds


class DeepForecaster:
    def __init__(
        self,
        model_type: str = "LSTM",
        seq_len: int = 12,     # Độ dài chuỗi lịch sử (vd: 12 bước x 5 phút = 60 phút)
        horizon: int = 3,       # Độ dài dự báo (vd: 3 bước x 5 phút = 15 phút, hoặc 6 bước = 30 phút)
        hidden_dim: int = 64,
        lr: float = 0.001,
        device: Optional[str] = None,
    ):
        self.seq_len = seq_len
        self.horizon = horizon
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = TrafficRNN(
            cell_type=model_type,
            input_dim=1,
            hidden_dim=hidden_dim,
            output_dim=horizon,
        ).to(self.device)
        self.criterion = nn.MSELoss()
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)

        # Lưu min, max để chuẩn hóa
        self.data_min = 0.0
        self.data_max = 1.0

    def create_sequences(self, data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        X, y = [], []
        for i in range(len(data) - self.seq_len - self.horizon + 1):
            X.append(data[i : i + self.seq_len])
            y.append(data[i + self.seq_len : i + self.seq_len + self.horizon])
        return np.array(X), np.array(y)

    def fit(self, series: np.ndarray, epochs: int = 30, batch_size: int = 16) -> Dict[str, List[float]]:
        self.data_min = float(np.min(series))
        self.data_max = float(np.max(series)) + 1e-6

        # Min-max scale [0, 1]
        norm_series = (series - self.data_min) / (self.data_max - self.data_min)
        X, y = self.create_sequences(norm_series)

        if len(X) == 0:
            raise ValueError("Chuỗi dữ liệu quá ngắn so với seq_len + horizon!")

        X_t = torch.tensor(X, dtype=torch.float32).unsqueeze(-1).to(self.device)
        y_t = torch.tensor(y, dtype=torch.float32).to(self.device)

        dataset = TensorDataset(X_t, y_t)
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

        history_loss = []
        self.model.train()
        for epoch in range(epochs):
            epoch_loss = 0.0
            for bx, by in loader:
                self.optimizer.zero_grad()
                pred = self.model(bx)
                loss = self.criterion(pred, by)
                loss.backward()
                self.optimizer.step()
                epoch_loss += loss.item()
            history_loss.append(epoch_loss / len(loader))

        return {"loss": history_loss}

    def predict(self, recent_history: np.ndarray) -> np.ndarray:
        self.model.eval()
        scaled = (recent_history[-self.seq_len :] - self.data_min) / (self.data_max - self.data_min)
        inp = torch.tensor(scaled, dtype=torch.float32).unsqueeze(0).unsqueeze(-1).to(self.device)
        with torch.no_grad():
            out = self.model(inp).cpu().numpy()[0]
        # Invert scale
        pred = out * (self.data_max - self.data_min) + self.data_min
        return np.maximum(0, pred)  # Số xe không âm


def evaluate_all_models(
    df: pd.DataFrame,
    target_col: str = "total_vehicles",
    horizon: int = 3,  # 3 bước (15 phút nếu nấc 5 min)
    seq_len: int = 12,
) -> pd.DataFrame:
    """Chạy so sánh Baseline vs Deep Learning trên chuỗi dữ liệu test."""
    values = df[target_col].values.astype(float)
    train_size = int(len(values) * 0.8)
    train_data = values[:train_size]
    test_data = values[train_size:]

    results = []

    # 1. Baseline: Persistence
    pers_preds, pers_trues = [], []
    for i in range(len(test_data) - horizon):
        hist = np.concatenate([train_data, test_data[: i + 1]])
        pred = BaselineForecaster.persistence(hist, horizon=horizon)
        true = test_data[i + 1 : i + 1 + horizon]
        pers_preds.append(pred)
        pers_trues.append(true)
    results.append({
        "Model": "Persistence",
        **calculate_metrics(np.array(pers_trues), np.array(pers_preds)),
    })

    # 2. Baseline: Seasonal Naive
    sn_preds, sn_trues = [], []
    for i in range(len(test_data) - horizon):
        hist = np.concatenate([train_data, test_data[: i + 1]])
        pred = BaselineForecaster.seasonal_naive(hist, season_length=12, horizon=horizon)
        true = test_data[i + 1 : i + 1 + horizon]
        sn_preds.append(pred)
        sn_trues.append(true)
    results.append({
        "Model": "Seasonal Naive",
        **calculate_metrics(np.array(sn_trues), np.array(sn_preds)),
    })

    # 3. Deep Learning: LSTM & GRU
    for m_type in ["LSTM", "GRU"]:
        forecaster = DeepForecaster(model_type=m_type, seq_len=seq_len, horizon=horizon)
        forecaster.fit(train_data, epochs=25)

        m_preds, m_trues = [], []
        for i in range(seq_len, len(test_data) - horizon):
            hist = test_data[i - seq_len : i]
            pred = forecaster.predict(hist)
            true = test_data[i : i + horizon]
            m_preds.append(pred)
            m_trues.append(true)

        results.append({
            "Model": m_type,
            **calculate_metrics(np.array(m_trues), np.array(m_preds)),
        })

    return pd.DataFrame(results)

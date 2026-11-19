"""Reproducible mock-data forecast experiment; run from any directory."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import torch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.forecasting import DeepForecaster, BaselineForecaster, calculate_metrics
from src.tracking import normalize_counts


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--epochs', type=int, default=25)
    p.add_argument('--output', type=Path, default=ROOT/'results/mock_forecast')
    args = p.parse_args()
    if args.epochs < 1:
        p.error('epochs must be positive')
    source = ROOT/'data/mock_traffic_data.csv'
    df = normalize_counts(pd.read_csv(source), 5)
    values = df.total_vehicles.to_numpy(dtype=float)
    split = int(len(values)*0.8)
    seq, horizon = 12, 6
    if split < seq+horizon or len(values)-split < horizon:
        raise ValueError('Insufficient training or test history')
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    args.output.mkdir(parents=True, exist_ok=True)
    models = {}
    losses = []
    for kind in ['LSTM', 'GRU']:
        torch.manual_seed(42)
        np.random.seed(42)
        model = DeepForecaster(model_type=kind, seq_len=seq, horizon=horizon, device='cpu')
        history = model.fit(values[:split], epochs=args.epochs)
        models[kind] = model
        losses.extend({'model':kind,'epoch':i+1,'training_mse_scaled':v} for i,v in enumerate(history['loss']))
        checkpoint = {'state_dict':model.model.state_dict(), 'model_type':kind, 'seq_len':seq,
                      'horizon':horizon,'hidden_dim':64,'data_min':model.data_min,'data_max':model.data_max,
                      'interval_minutes':5,'data_source':'synthetic','train_rows':split}
        path = args.output/f'{kind.lower()}.pt'
        torch.save(checkpoint,path)
        saved = torch.load(path, map_location='cpu', weights_only=True)
        restored = DeepForecaster(model_type=kind, seq_len=seq, horizon=horizon, device='cpu')
        restored.model.load_state_dict(saved['state_dict'])
        restored.data_min, restored.data_max = saved['data_min'], saved['data_max']
        np.testing.assert_allclose(model.predict(values[:split]), restored.predict(values[:split]), atol=1e-6)
        print(f'{kind}: trained and checkpoint reload verified', flush=True)
    predictions = []
    # All methods use identical forecast origins and only observations available
    # before that origin. Models/scalers are fit only on the first 80 percent.
    for origin in range(split,len(values)-horizon+1):
        history = values[:origin]
        forecasts = {
            'Persistence':BaselineForecaster.persistence(history,horizon),
            'Moving average':BaselineForecaster.moving_average(history,window=6,horizon=horizon),
            'Seasonal naive (1h)':BaselineForecaster.seasonal_naive(history,season_length=12,horizon=horizon),
            **{kind:model.predict(history) for kind,model in models.items()}}
        for kind, forecast in forecasts.items():
            for step, pred in enumerate(forecast,1):
                predictions.append({'model':kind,'origin_timestamp':df.timestamp.iloc[origin-1],
                                    'target_timestamp':df.timestamp.iloc[origin+step-1],
                                    'horizon_minutes':step*5,'actual':values[origin+step-1], 'prediction':float(pred)})
    predictions = pd.DataFrame(predictions)
    metrics = []
    for (kind, minutes), group in predictions.groupby(['model','horizon_minutes']):
        metrics.append({'model':kind,'horizon_minutes':int(minutes),'samples':len(group),
                        **calculate_metrics(group.actual.to_numpy(),group.prediction.to_numpy())})
    metrics = pd.DataFrame(metrics)
    assert predictions.groupby('model').size().nunique()==1
    assert np.isfinite(predictions[['actual','prediction']].to_numpy()).all()
    predictions.to_csv(args.output/'test_predictions.csv',index=False)
    metrics.to_csv(args.output/'metrics.csv',index=False)
    pd.DataFrame(losses).to_csv(args.output/'training_loss.csv',index=False)
    # A demonstration forecast from the latest observations, with no claimed truth.
    future=[]
    for kind,model in models.items():
        for step,pred in enumerate(model.predict(values),1):
            future.append({'model':kind,'timestamp':df.timestamp.iloc[-1]+pd.Timedelta(minutes=step*5),
                           'horizon_minutes':step*5,'prediction':float(pred),'data_source':'synthetic'})
    pd.DataFrame(future).to_csv(args.output/'demo_future_forecast.csv',index=False)
    report={'data_source':'synthetic mock data; not real traffic performance','source':str(source),
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'seed':42,'epochs':args.epochs,
            'train_rows':split,'test_rows':len(values)-split,'train_end':str(df.timestamp.iloc[split-1]),
            'test_start':str(df.timestamp.iloc[split]),'forecast_origins_per_model':len(values)-horizon-split+1,
            'history_minutes':60,'horizon_minutes':30,'interval_minutes':5,
            'checkpoint_roundtrip':'passed','protocol':'Chronological 80/20 split; fixed training; identical rolling origins for all methods; scaler fitted on train only.',
            'limitations':['One synthetic day cannot establish generalization.','Overlapping forecast windows are not independent samples.',
                           'No tuning or model selection performed on test data.','Seasonal naive uses a one-hour lag, not a daily cycle.',
                           'MAPE excludes zero targets; all-zero targets are reported as zero by the existing metric helper.'],
            'versions':{'torch':torch.__version__,'pandas':pd.__version__,'numpy':np.__version__}}
    (args.output/'experiment.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(metrics[metrics.horizon_minutes.isin([15,30])].to_string(index=False))


if __name__=='__main__':
    main()

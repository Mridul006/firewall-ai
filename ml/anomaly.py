"""Isolation Forest anomaly detector: train, score, and flag anomalous traffic."""

import logging
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest

from config import settings
from features import FEATURE_COLUMNS

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_PATH = MODEL_DIR / "isolation_forest.joblib"


def train(features: pd.DataFrame) -> IsolationForest:
    """Fit a new Isolation Forest on the given feature matrix and persist it to disk."""
    model = IsolationForest(
        n_estimators=100,
        contamination=settings.ANOMALY_CONTAMINATION,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(features[FEATURE_COLUMNS])

    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    logger.info(f"Trained Isolation Forest on {len(features)} rows, saved to {MODEL_PATH}")
    return model


def load_model() -> IsolationForest:
    """Load the persisted Isolation Forest model from disk.

    Call this once at startup and reuse the returned model — never retrain
    on every request.
    """
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"No trained model at {MODEL_PATH} — run train() first")
    return joblib.load(MODEL_PATH)


def score(model: IsolationForest, features: pd.DataFrame) -> pd.DataFrame:
    """Score each row's anomaly level and append an anomaly_score column.

    IsolationForest.score_samples() returns higher values for more normal
    points, so the sign is flipped and min-max normalized to 0.0 (normal) ..
    1.0 (highly anomalous), matching the scale used in layer1_design.md.
    """
    raw_scores = model.score_samples(features[FEATURE_COLUMNS])
    spread = raw_scores.max() - raw_scores.min()
    normalized = 1 - (raw_scores - raw_scores.min()) / (spread if spread > 0 else 1e-9)

    result = features.copy()
    result["anomaly_score"] = normalized
    logger.info(
        f"Scored {len(features)} rows — "
        f"min={normalized.min():.3f} max={normalized.max():.3f} mean={normalized.mean():.3f}"
    )
    return result


def detect_anomalies(
    model: IsolationForest, features: pd.DataFrame, threshold: float = 0.5
) -> pd.DataFrame:
    """Return only the rows whose anomaly_score exceeds the given threshold."""
    scored = score(model, features)
    anomalies = scored[scored["anomaly_score"] > threshold]
    logger.info(f"Detected {len(anomalies)}/{len(scored)} anomalous rows above threshold {threshold}")
    return anomalies

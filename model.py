from tensorflow.keras import Sequential
from tensorflow.keras.layers import Dense, LSTM


def build_lstm_model(timesteps: int, features: int = 1):
    """Build a simple LSTM regressor for next-step forecasting."""
    model = Sequential(
        [
            LSTM(64, input_shape=(timesteps, features)),
            Dense(32, activation="relu"),
            Dense(1),
        ]
    )
    model.compile(optimizer="adam", loss="mse")
    return model

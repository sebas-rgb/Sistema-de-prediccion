try:
    import torch
    from torch import nn
except ImportError as exc:
    raise RuntimeError(
        "PyTorch no esta disponible en el interprete actual. "
        "Instala las dependencias con un entorno compatible, idealmente Python 3.12, "
        "antes de ejecutar el forecasting."
    ) from exc


class InventoryForecastGRU(nn.Module):
    """Compact GRU regressor for daily stock forecasting."""

    def __init__(
        self,
        input_size: int,
        hidden_size: int = 64,
        num_layers: int = 1,
        dropout: float = 0.0,
    ) -> None:
        super().__init__()
        gru_dropout = dropout if num_layers > 1 else 0.0
        self.gru = nn.GRU(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=gru_dropout,
        )
        self.regressor = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        gru_out, _ = self.gru(inputs)
        last_state = gru_out[:, -1, :]
        return self.regressor(last_state).squeeze(-1)

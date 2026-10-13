"""Price contract: market price (EUR/kWh, ex tax) -> consumer import/export price.

Zonneplan-style formulas (see plan). Quarter-hour is the time unit.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PriceModel:
    vat: float = 1.21
    energy_tax: float = 0.11085      # EUR/kWh incl. in import
    import_markup: float = 0.02
    export_markup: float = 0.02
    salderen: bool = True            # 2026 rules; False = 2027 rules (no netting)

    def import_price(self, market: float) -> float:
        return market * self.vat + self.energy_tax + self.import_markup

    def export_price(self, market: float) -> float:
        if self.salderen:
            return market * 1.10 * self.vat + self.export_markup + self.energy_tax
        return market * 1.10 + self.export_markup


def curves(market: list[float], model: PriceModel) -> tuple[list[float], list[float]]:
    return [model.import_price(m) for m in market], [model.export_price(m) for m in market]

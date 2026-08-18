from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# =========================================================
# RR TRADER — STRICT TRADE ENGINE
# =========================================================
#
# PURPOSE
# -------
# This engine converts a structured RR Trader signal into:
#
#   NO_TRADE
#   WATCH
#   EXECUTE_CANDIDATE
#
# It evaluates 24 independent trading-quality areas.
#
# IMPORTANT
# ---------
# This version is PAPER-TRADING ONLY.
#
# It does NOT send real Binance orders.
#
# The engine is designed so that live execution can later
# be connected behind the same trade gate.
#
# A 95% or 100% trade score does NOT guarantee profit.
# It means the programmed confirmation rules have passed.
# =========================================================


# =========================================================
# CONFIG
# =========================================================

@dataclass
class TradeConfig:
    """
    Strict trade-engine configuration.
    """

    enabled: bool = True

    mode: str = "paper"

    # Minimum aggregate quality for an EXECUTE candidate.
    execute_threshold: float = 95.0

    # Minimum quality for WATCH.
    watch_threshold: float = 90.0

    # Required independent confirmation groups.
    minimum_confirmations: int = 8

    # Risk settings.
    risk_per_trade_percent: float = 0.5

    max_open_positions: int = 2

    max_daily_loss_percent: float = 2.0

    minimum_risk_reward: float = 1.5

    # Execution filters.
    max_spread_percent: float = 0.15

    max_slippage_percent: float = 0.20

    max_signal_age_seconds: int = 120

    # Market rules.
    allow_long: bool = True

    allow_short: bool = True

    # Require explicit data for important checks.
    require_news_check: bool = False

    require_market_context: bool = True

    require_entry_location: bool = True

    require_stop_quality: bool = True

    require_risk_reward: bool = True

    require_signal_freshness: bool = True


# =========================================================
# POSITION
# =========================================================

@dataclass
class PaperPosition:
    """
    Simulated paper position.
    """

    id: str

    symbol: str

    market: str

    direction: str

    entry_price: float

    quantity: float

    stop_loss: float

    tp1: float

    tp2: float

    tp3: float

    confidence: float

    trade_score: float

    confirmations: int

    risk_amount: float

    opened_at: str

    status: str = "OPEN"

    realized_pnl: float = 0.0

    tp1_hit: bool = False

    tp2_hit: bool = False

    tp3_hit: bool = False


# =========================================================
# CONFIRMATION RESULT
# =========================================================

@dataclass
class Confirmation:
    """
    One confirmation group.
    """

    name: str

    passed: bool

    weight: float

    score: float

    critical: bool

    reason: str


# =========================================================
# TRADE ENGINE
# =========================================================

class TradeEngine:
    """
    Strict RR Trader trade-decision and paper-position engine.

    24 confirmation groups are evaluated before a trade
    can become an EXECUTE candidate.
    """

    def __init__(
        self,
        starting_balance: float = 1000.0,
        config: Optional[TradeConfig] = None,
    ) -> None:

        self.config = (
            config
            or TradeConfig()
        )

        self.starting_balance = float(
            starting_balance
        )

        self.balance = float(
            starting_balance
        )

        self.positions: Dict[
            str,
            PaperPosition,
        ] = {}

        self.closed_trades: List[
            Dict[str, Any]
        ] = []

        self.daily_realized_pnl = 0.0

        self.last_signal: Optional[
            Dict[str, Any]
        ] = None

        self.last_decision: Optional[
            Dict[str, Any]
        ] = None

    # =====================================================
    # BASIC HELPERS
    # =====================================================

    @staticmethod
    def _safe_float(
        value: Any,
        default: float = 0.0,
    ) -> float:

        try:
            return float(value)

        except (
            TypeError,
            ValueError,
        ):

            return default

    @staticmethod
    def _safe_bool(
        value: Any,
        default: bool = False,
    ) -> bool:

        if isinstance(
            value,
            bool,
        ):
            return value

        if value is None:
            return default

        if isinstance(
            value,
            str,
        ):

            normalized = (
                value
                .strip()
                .lower()
            )

            if normalized in {
                "true",
                "yes",
                "pass",
                "passed",
                "bullish",
                "bearish",
                "long",
                "short",
                "valid",
                "strong",
            }:
                return True

            if normalized in {
                "false",
                "no",
                "fail",
                "failed",
                "neutral",
                "invalid",
                "weak",
            }:
                return False

        return bool(
            value
        )

    @staticmethod
    def _now() -> str:

        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _normalize_symbol(
        symbol: Any,
    ) -> str:

        cleaned = (
            str(
                symbol
                or ""
            )
            .upper()
            .replace(
                "/",
                "",
            )
            .replace(
                "-",
                "",
            )
            .strip()
        )

        if cleaned and not cleaned.endswith(
            "USDT"
        ):
            cleaned = (
                f"{cleaned}USDT"
            )

        return cleaned

    @staticmethod
    def _value(
        signal: Dict[str, Any],
        *names: str,
        default: Any = None,
    ) -> Any:

        for name in names:

            if name in signal:

                value = signal[
                    name
                ]

                if value is not None:
                    return value

        return default

    # =====================================================
    # MARKET / POSITION STATE
    # =====================================================

    def get_config(
        self,
    ) -> Dict[str, Any]:

        return asdict(
            self.config
        )

    def update_config(
        self,
        **kwargs: Any,
    ) -> Dict[str, Any]:

        for key, value in kwargs.items():

            if hasattr(
                self.config,
                key,
            ):

                setattr(
                    self.config,
                    key,
                    value,
                )

        return self.get_config()

    def get_balance(
        self,
    ) -> float:

        return round(
            self.balance,
            8,
        )

    def get_open_positions(
        self,
    ) -> List[Dict[str, Any]]:

        return [
            asdict(
                position
            )
            for position
            in self.positions.values()
        ]

    def get_closed_trades(
        self,
    ) -> List[Dict[str, Any]]:

        return list(
            self.closed_trades
        )

    def get_status(
        self,
    ) -> Dict[str, Any]:

        return {
            "enabled": (
                self.config.enabled
            ),
            "mode": (
                self.config.mode
            ),
            "balance": (
                self.get_balance()
            ),
            "starting_balance": (
                self.starting_balance
            ),
            "daily_realized_pnl": round(
                self.daily_realized_pnl,
                8,
            ),
            "daily_loss_percent": round(
                self._daily_loss_percent(),
                4,
            ),
            "open_positions": len(
                self.positions
            ),
            "max_open_positions": (
                self.config.max_open_positions
            ),
            "last_signal": (
                self.last_signal
            ),
            "last_decision": (
                self.last_decision
            ),
        }

    # =====================================================
    # DAILY RISK
    # =====================================================

    def _daily_loss_percent(
        self,
    ) -> float:

        if (
            self.starting_balance
            <= 0
        ):
            return 0.0

        loss = min(
            0.0,
            self.daily_realized_pnl,
        )

        return (
            abs(loss)
            / self.starting_balance
            * 100.0
        )

    def _daily_loss_limit_reached(
        self,
    ) -> bool:

        return (
            self._daily_loss_percent()
            >= self.config.max_daily_loss_percent
        )

    def _risk_amount(
        self,
    ) -> float:

        return (
            self.balance
            * (
                self.config.risk_per_trade_percent
                / 100.0
            )
        )

    # =====================================================
    # 1. MARKET REGIME
    # =====================================================

    def _check_market_regime(
        self,
        signal: Dict[str, Any],
        direction: str,
    ) -> Confirmation:

        regime = str(
            self._value(
                signal,
                "market_regime",
                "regime",
                default="",
            )
            or ""
        ).upper()

        strength = self._safe_float(
            self._value(
                signal,
                "regime_strength",
                default=0,
            )
        )

        aligned = (
            regime in {
                "TREND_UP",
                "TRENDING_UP",
                "BULLISH",
            }
            if direction == "LONG"
            else regime in {
                "TREND_DOWN",
                "TRENDING_DOWN",
                "BEARISH",
            }
        )

        passed = (
            aligned
            and strength >= 50
        )

        return Confirmation(
            name="market_regime",
            passed=passed,
            weight=5.0,
            score=(
                5.0
                if passed
                else 0.0
            ),
            critical=True,
            reason=(
                f"Regime={regime or 'UNKNOWN'}, "
                f"strength={strength:.1f}"
            ),
        )

    # =====================================================
    # 2. MARKET STRUCTURE
    # =====================================================

    def _check_market_structure(
        self,
        signal: Dict[str, Any],
        direction: str,
    ) -> Confirmation:

        structure = str(
            self._value(
                signal,
                "market_structure",
                "structure",
                default="",
            )
            or ""
        ).upper()

        bullish_values = {
            "BULLISH",
            "HH_HL",
            "HH+HL",
            "HIGHER_HIGH_HIGHER_LOW",
            "BREAK_OF_STRUCTURE_UP",
            "BOS_UP",
        }

        bearish_values = {
            "BEARISH",
            "LH_LL",
            "LH+LL",
            "LOWER_HIGH_LOWER_LOW",
            "BREAK_OF_STRUCTURE_DOWN",
            "BOS_DOWN",
        }

        passed = (
            structure in (
                bullish_values
                if direction == "LONG"
                else bearish_values
            )
        )

        return Confirmation(
            name="market_structure",
            passed=passed,
            weight=6.0,
            score=(
                6.0
                if passed
                else 0.0
            ),
            critical=True,
            reason=(
                f"Structure={structure or 'UNKNOWN'}"
            ),
        )

    # =====================================================
    # 3. MULTI TIMEFRAME ALIGNMENT
    # =====================================================

    def _check_multi_timeframe(
        self,
        signal: Dict[str, Any],
        direction: str,
    ) -> Confirmation:

        timeframes = self._value(
            signal,
            "timeframes",
            "mtf",
            "multi_timeframe",
            default={},
        )

        if not isinstance(
            timeframes,
            dict,
        ):

            return Confirmation(
                name="multi_timeframe",
                passed=False,
                weight=7.0,
                score=0.0,
                critical=True,
                reason="MTF data missing.",
            )

        required = [
            "5m",
            "15m",
            "1h",
            "4h",
        ]

        aligned = 0

        for timeframe in required:

            item = timeframes.get(
                timeframe,
                {}
            )

            if isinstance(
                item,
                dict,
            ):

                item_direction = str(
                    self._value(
                        item,
                        "direction",
                        default="",
                    )
                    or ""
                ).upper()

            else:

                item_direction = str(
                    item
                    or ""
                ).upper()

            if (
                item_direction
                == direction
            ):

                aligned += 1

        # Strongest MTF quality:
        # at least 3/4 aligned and 4H aligned.

        four_hour = timeframes.get(
            "4h",
            {},
        )

        four_hour_direction = ""

        if isinstance(
            four_hour,
            dict,
        ):

            four_hour_direction = str(
                self._value(
                    four_hour,
                    "direction",
                    default="",
                )
                or ""
            ).upper()

        passed = (
            aligned >= 3
            and four_hour_direction
            == direction
        )

        return Confirmation(
            name="multi_timeframe",
            passed=passed,
            weight=7.0,
            score=(
                min(
                    7.0,
                    aligned
                    / 4.0
                    * 7.0,
                )
            ),
            critical=True,
            reason=(
                f"{aligned}/4 timeframes aligned; "
                f"4H={four_hour_direction or 'UNKNOWN'}"
            ),
        )

    # =====================================================
    # 4. ENTRY LOCATION
    # =====================================================

    def _check_entry_location(
        self,
        signal: Dict[str, Any],
        direction: str,
    ) -> Confirmation:

        if not self.config.require_entry_location:

            return Confirmation(
                name="entry_location",
                passed=True,
                weight=5.0,
                score=5.0,
                critical=False,
                reason="Entry-location requirement disabled.",
            )

        quality = self._safe_float(
            self._value(
                signal,
                "entry_quality_score",
                "entry_location_score",
                default=0,
            )
        )

        extended = self._safe_bool(
            self._value(
                signal,
                "entry_extended",
                "is_extended",
                default=False,
            )
        )

        near_support = self._safe_bool(
            self._value(
                signal,
                "near_support",
                "near_demand",
                default=False,
            )
        )

        near_resistance = self._safe_bool(
            self._value(
                signal,
                "near_resistance",
                "near_supply",
                default=False,
            )
        )

        if direction == "LONG":

            location_ok = (
                not near_resistance
                and (
                    near_support
                    or quality >= 70
                )
            )

        else:

            location_ok = (
                not near_support
                and (
                    near_resistance
                    or quality >= 70
                )
            )

        passed = (
            location_ok
            and not extended
        )

        return Confirmation(
            name="entry_location",
            passed=passed,
            weight=5.0,
            score=(
                5.0
                if passed
                else 0.0
            ),
            critical=True,
            reason=(
                f"quality={quality:.1f}, "
                f"extended={extended}, "
                f"support={near_support}, "
                f"resistance={near_resistance}"
            ),
        )

    # =====================================================
    # 5. LIQUIDITY / STOP HUNT
    # =====================================================

    def _check_liquidity(
        self,
        signal: Dict[str, Any],
        direction: str,
    ) -> Confirmation:

        sweep_direction = str(
            self._value(
                signal,
                "liquidity_sweep",
                "liquidity_event",
                default="",
            )
            or ""
        ).upper()

        sweep_valid = self._safe_bool(
            self._value(
                signal,
                "liquidity_sweep_valid",
                "sweep_confirmed",
                default=False,
            )
        )

        stop_hunt = self._safe_bool(
            self._value(
                signal,
                "stop_hunt_risk",
                default=False,
            )
        )

        favorable = (
            (
                direction == "LONG"
                and sweep_direction
                in {
                    "",
                    "LOW_SWEEP",
                    "SELLSIDE_SWEEP",
                    "BULLISH_SWEEP",
                }
            )
            or
            (
                direction == "SHORT"
                and sweep_direction
                in {
                    "",
                    "HIGH_SWEEP",
                    "BUYSIDE_SWEEP",
                    "BEARISH_SWEEP",
                }
            )
        )

        passed = (
            favorable
            and not stop_hunt
        )

        return Confirmation(
            name="liquidity",
            passed=passed,
            weight=4.0,
            score=(
                4.0
                if passed
                else 0.0
            ),
            critical=False,
            reason=(
                f"sweep={sweep_direction or 'NONE'}, "
                f"valid={sweep_valid}, "
                f"stop_hunt_risk={stop_hunt}"
            ),
        )

    # =====================================================
    # 6. VWAP / FAIR VALUE
    # =====================================================

    def _check_vwap(
        self,
        signal: Dict[str, Any],
        direction: str,
    ) -> Confirmation:

        price = self._safe_float(
            self._value(
                signal,
                "price",
                "current_price",
                default=0,
            )
        )

        vwap = self._safe_float(
            self._value(
                signal,
                "vwap",
                default=0,
            )
        )

        if (
            price <= 0
            or vwap <= 0
        ):

            return Confirmation(
                name="vwap_fair_value",
                passed=False,
                weight=3.0,
                score=0.0,
                critical=False,
                reason="VWAP data missing.",
            )

        tolerance = abs(
            price - vwap
        ) / price * 100.0

        passed = (
            (
                direction == "LONG"
                and price >= vwap
            )
            or
            (
                direction == "SHORT"
                and price <= vwap
            )
        ) and tolerance <= 8.0

        return Confirmation(
            name="vwap_fair_value",
            passed=passed,
            weight=3.0,
            score=(
                3.0
                if passed
                else 0.0
            ),
            critical=False,
            reason=(
                f"price={price:.6f}, "
                f"vwap={vwap:.6f}, "
                f"distance={tolerance:.2f}%"
            ),
        )

    # =====================================================
    # 7. ATR / VOLATILITY
    # =====================================================

    def _check_volatility(
        self,
        signal: Dict[str, Any],
    ) -> Confirmation:

        atr_percent = self._safe_float(
            self._value(
                signal,
                "atr_percent",
                "atr_pct",
                default=0,
            )
        )

        volatility_ok = self._safe_bool(
            self._value(
                signal,
                "volatility_ok",
                default=False,
            )
        )

        # Accept explicit flag, or a sensible ATR range.
        passed = (
            volatility_ok
            or (
                0.10
                <= atr_percent
                <= 12.0
            )
        )

        return Confirmation(
            name="atr_volatility",
            passed=passed,
            weight=3.0,
            score=(
                3.0
                if passed
                else 0.0
            ),
            critical=False,
            reason=(
                f"ATR={atr_percent:.3f}%"
            ),
        )

    # =====================================================
    # 8. MOMENTUM
    # =====================================================

    def _check_momentum(
        self,
        signal: Dict[str, Any],
        direction: str,
    ) -> Confirmation:

        momentum = str(
            self._value(
                signal,
                "momentum",
                "momentum_direction",
                default="",
            )
            or ""
        ).upper()

        momentum_score = self._safe_float(
            self._value(
                signal,
                "momentum_score",
                default=0,
            )
        )

        aligned = (
            (
                direction == "LONG"
                and momentum
                in {
                    "BULLISH",
                    "STRONG",
                    "UP",
                    "LONG",
                }
            )
            or
            (
                direction == "SHORT"
                and momentum
                in {
                    "BEARISH",
                    "STRONG",
                    "DOWN",
                    "SHORT",
                }
            )
        )

        passed = (
            aligned
            and momentum_score >= 50
        )

        return Confirmation(
            name="momentum",
            passed=passed,
            weight=4.0,
            score=(
                4.0
                if passed
                else 0.0
            ),
            critical=False,
            reason=(
                f"momentum={momentum or 'UNKNOWN'}, "
                f"score={momentum_score:.1f}"
            ),
        )

    # =====================================================
    # 9. DIVERGENCE
    # =====================================================

    def _check_divergence(
        self,
        signal: Dict[str, Any],
        direction: str,
    ) -> Confirmation:

        divergence = str(
            self._value(
                signal,
                "divergence",
                default="NONE",
            )
            or "NONE"
        ).upper()

        harmful = (
            (
                direction == "LONG"
                and divergence
                in {
                    "BEARISH",
                    "NEGATIVE",
                }
            )
            or
            (
                direction == "SHORT"
                and divergence
                in {
                    "BULLISH",
                    "POSITIVE",
                }
            )
        )

        passed = not harmful

        return Confirmation(
            name="divergence",
            passed=passed,
            weight=3.0,
            score=(
                3.0
                if passed
                else 0.0
            ),
            critical=False,
            reason=(
                f"divergence={divergence}"
            ),
        )

    # =====================================================
    # 10. BREAKOUT QUALITY
    # =====================================================

    def _check_breakout(
        self,
        signal: Dict[str, Any],
        direction: str,
    ) -> Confirmation:

        breakout = self._safe_bool(
            self._value(
                signal,
                "breakout_confirmed",
                "breakout_valid",
                default=False,
            )
        )

        close_confirmed = self._safe_bool(
            self._value(
                signal,
                "breakout_close_confirmed",
                default=False,
            )
        )

        false_breakout = self._safe_bool(
            self._value(
                signal,
                "false_breakout",
                "failed_breakout",
                default=False,
            )
        )

        # If this is not a breakout trade, do not force it.
        breakout_required = self._safe_bool(
            self._value(
                signal,
                "breakout_trade",
                default=False,
            )
        )

        if not breakout_required:

            return Confirmation(
                name="breakout_quality",
                passed=True,
                weight=3.0,
                score=3.0,
                critical=False,
                reason="Breakout confirmation not required.",
            )

        passed = (
            breakout
            and close_confirmed
            and not false_breakout
        )

        return Confirmation(
            name="breakout_quality",
            passed=passed,
            weight=3.0,
            score=(
                3.0
                if passed
                else 0.0
            ),
            critical=False,
            reason=(
                f"breakout={breakout}, "
                f"close={close_confirmed}, "
                f"false_breakout={false_breakout}"
            ),
        )

    # =====================================================
    # 11. RETEST QUALITY
    # =====================================================

    def _check_retest(
        self,
        signal: Dict[str, Any],
    ) -> Confirmation:

        retest_required = self._safe_bool(
            self._value(
                signal,
                "retest_required",
                default=False,
            )
        )

        if not retest_required:

            return Confirmation(
                name="retest_quality",
                passed=True,
                weight=3.0,
                score=3.0,
                critical=False,
                reason="Retest not required.",
            )

        retest_confirmed = self._safe_bool(
            self._value(
                signal,
                "retest_confirmed",
                default=False,
            )
        )

        retest_hold = self._safe_bool(
            self._value(
                signal,
                "retest_hold",
                "level_held",
                default=False,
            )
        )

        passed = (
            retest_confirmed
            and retest_hold
        )

        return Confirmation(
            name="retest_quality",
            passed=passed,
            weight=3.0,
            score=(
                3.0
                if passed
                else 0.0
            ),
            critical=False,
            reason=(
                f"confirmed={retest_confirmed}, "
                f"hold={retest_hold}"
            ),
        )

    # =====================================================
    # 12. DERIVATIVES POSITIONING
    # =====================================================

    def _check_derivatives(
        self,
        signal: Dict[str, Any],
        direction: str,
    ) -> Confirmation:

        positioning = str(
            self._value(
                signal,
                "derivatives_bias",
                "derivatives_direction",
                default="",
            )
            or ""
        ).upper()

        oi_price_relationship = str(
            self._value(
                signal,
                "oi_price_relationship",
                default="",
            )
            or ""
        ).upper()

        funding = self._safe_float(
            self._value(
                signal,
                "funding_rate",
                default=0,
            )
        )

        direction_ok = (
            (
                direction == "LONG"
                and positioning
                in {
                    "",
                    "BULLISH",
                    "LONG",
                    "POSITIVE",
                }
            )
            or
            (
                direction == "SHORT"
                and positioning
                in {
                    "",
                    "BEARISH",
                    "SHORT",
                    "NEGATIVE",
                }
            )
        )

        oi_ok = (
            oi_price_relationship
            not in {
                "CONTRADICTING",
                "STRONG_CONTRADICTION",
            }
        )

        funding_extreme = abs(
            funding
        ) > 0.005

        passed = (
            direction_ok
            and oi_ok
            and not funding_extreme
        )

        return Confirmation(
            name="derivatives",
            passed=passed,
            weight=6.0,
            score=(
                6.0
                if passed
                else 0.0
            ),
            critical=True,
            reason=(
                f"bias={positioning or 'UNKNOWN'}, "
                f"OI/price={oi_price_relationship or 'UNKNOWN'}, "
                f"funding={funding:.6f}"
            ),
        )

    # =====================================================
    # 13. LIQUIDATION CONTEXT
    # =====================================================

    def _check_liquidations(
        self,
        signal: Dict[str, Any],
        direction: str,
    ) -> Confirmation:

        liquidation_bias = str(
            self._value(
                signal,
                "liquidation_bias",
                "liquidation_context",
                default="",
            )
            or ""
        ).upper()

        contradiction = self._safe_bool(
            self._value(
                signal,
                "liquidation_contradiction",
                default=False,
            )
        )

        favorable = (
            liquidation_bias
            in {
                "",
                "NEUTRAL",
                "BULLISH"
                if direction == "LONG"
                else "BEARISH",
            }
        )

        passed = (
            favorable
            and not contradiction
        )

        return Confirmation(
            name="liquidation_context",
            passed=passed,
            weight=4.0,
            score=(
                4.0
                if passed
                else 0.0
            ),
            critical=False,
            reason=(
                f"bias={liquidation_bias or 'UNKNOWN'}, "
                f"contradiction={contradiction}"
            ),
        )

    # =====================================================
    # 14. ORDER BOOK
    # =====================================================

    def _check_order_book(
        self,
        signal: Dict[str, Any],
        direction: str,
    ) -> Confirmation:

        imbalance = self._safe_float(
            self._value(
                signal,
                "order_book_imbalance",
                "book_imbalance",
                default=0,
            )
        )

        absorption = str(
            self._value(
                signal,
                "order_book_absorption",
                "absorption",
                default="",
            )
            or ""
        ).upper()

        # Very simple directional interpretation:
        # positive = bid/buyer dominance
        # negative = ask/seller dominance.

        directional_ok = (
            (
                direction == "LONG"
                and imbalance > 0
            )
            or
            (
                direction == "SHORT"
                and imbalance < 0
            )
        )

        absorption_ok = (
            absorption
            not in {
                "CONTRADICTING",
                "SELLER_ABSORPTION"
                if direction == "LONG"
                else "BUYER_ABSORPTION",
            }
        )

        passed = (
            directional_ok
            and absorption_ok
        )

        return Confirmation(
            name="order_book",
            passed=passed,
            weight=5.0,
            score=(
                5.0
                if passed
                else 0.0
            ),
            critical=True,
            reason=(
                f"imbalance={imbalance:.4f}, "
                f"absorption={absorption or 'UNKNOWN'}"
            ),
        )

    # =====================================================
    # 15. TRADEABILITY
    # =====================================================

    def _check_tradeability(
        self,
        signal: Dict[str, Any],
    ) -> Confirmation:

        spread = self._safe_float(
            self._value(
                signal,
                "spread_percent",
                "spread_pct",
                default=0,
            )
        )

        liquidity = self._safe_float(
            self._value(
                signal,
                "liquidity_score",
                default=0,
            )
        )

        slippage = self._safe_float(
            self._value(
                signal,
                "expected_slippage_percent",
                "slippage_percent",
                default=0,
            )
        )

        passed = (
            spread
            <= self.config.max_spread_percent
            and slippage
            <= self.config.max_slippage_percent
            and (
                liquidity >= 50
                or liquidity == 0
            )
        )

        return Confirmation(
            name="tradeability",
            passed=passed,
            weight=4.0,
            score=(
                4.0
                if passed
                else 0.0
            ),
            critical=True,
            reason=(
                f"spread={spread:.4f}%, "
                f"slippage={slippage:.4f}%, "
                f"liquidity={liquidity:.1f}"
            ),
        )

    # =====================================================
    # 16. NEWS / EVENTS
    # =====================================================

    def _check_news(
        self,
        signal: Dict[str, Any],
    ) -> Confirmation:

        if not self.config.require_news_check:

            # If news is not configured yet,
            # it should not falsely block trading.
            return Confirmation(
                name="news_event_risk",
                passed=True,
                weight=3.0,
                score=3.0,
                critical=False,
                reason="News gate not configured.",
            )

        event_risk = str(
            self._value(
                signal,
                "news_risk",
                "event_risk",
                default="UNKNOWN",
            )
            or "UNKNOWN"
        ).upper()

        major_event = self._safe_bool(
            self._value(
                signal,
                "major_news_event",
                default=False,
            )
        )

        passed = (
            event_risk
            not in {
                "HIGH",
                "EXTREME",
            }
            and not major_event
        )

        return Confirmation(
            name="news_event_risk",
            passed=passed,
            weight=3.0,
            score=(
                3.0
                if passed
                else 0.0
            ),
            critical=True,
            reason=(
                f"risk={event_risk}, "
                f"major_event={major_event}"
            ),
        )

    # =====================================================
    # 17. MARKET CONTEXT
    # =====================================================

    def _check_market_context(
        self,
        signal: Dict[str, Any],
        direction: str,
    ) -> Confirmation:

        if not self.config.require_market_context:

            return Confirmation(
                name="market_context",
                passed=True,
                weight=4.0,
                score=4.0,
                critical=False,
                reason="Market-context gate disabled.",
            )

        btc_bias = str(
            self._value(
                signal,
                "btc_bias",
                "market_bias",
                default="",
            )
            or ""
        ).upper()

        if btc_bias in {
            "",
            "NEUTRAL",
        }:

            return Confirmation(
                name="market_context",
                passed=True,
                weight=4.0,
                score=4.0,
                critical=False,
                reason=(
                    "No conflicting BTC/market bias."
                ),
            )

        aligned = (
            (
                direction == "LONG"
                and btc_bias
                in {
                    "BULLISH",
                    "LONG",
                    "UP",
                }
            )
            or
            (
                direction == "SHORT"
                and btc_bias
                in {
                    "BEARISH",
                    "SHORT",
                    "DOWN",
                }
            )
        )

        return Confirmation(
            name="market_context",
            passed=aligned,
            weight=4.0,
            score=(
                4.0
                if aligned
                else 0.0
            ),
            critical=True,
            reason=(
                f"BTC/market bias="
                f"{btc_bias}"
            ),
        )

    # =====================================================
    # 18. RELATIVE STRENGTH
    # =====================================================

    def _check_relative_strength(
        self,
        signal: Dict[str, Any],
        direction: str,
    ) -> Confirmation:

        relative = self._safe_float(
            self._value(
                signal,
                "relative_strength",
                "relative_strength_score",
                default=0,
            )
        )

        passed = (
            (
                direction == "LONG"
                and relative >= 50
            )
            or
            (
                direction == "SHORT"
                and relative <= 50
            )
            or
            relative == 0
        )

        return Confirmation(
            name="relative_strength",
            passed=passed,
            weight=3.0,
            score=(
                3.0
                if passed
                else 0.0
            ),
            critical=False,
            reason=(
                f"relative_strength={relative:.1f}"
            ),
        )

    # =====================================================
    # 19. RISK / REWARD
    # =====================================================

    def _check_risk_reward(
        self,
        signal: Dict[str, Any],
    ) -> Confirmation:

        rr = self._safe_float(
            self._value(
                signal,
                "risk_reward",
                "rr",
                default=0,
            )
        )

        if not self.config.require_risk_reward:

            return Confirmation(
                name="risk_reward",
                passed=True,
                weight=6.0,
                score=6.0,
                critical=False,
                reason="R:R requirement disabled.",
            )

        passed = (
            rr
            >= self.config.minimum_risk_reward
        )

        # More reward gets a better quality score.
        score = min(
            6.0,
            max(
                0.0,
                rr
                / max(
                    1.0,
                    self.config.minimum_risk_reward,
                )
                * 3.0,
            ),
        )

        if passed:

            score = min(
                6.0,
                max(
                    score,
                    4.0,
                ),
            )

        return Confirmation(
            name="risk_reward",
            passed=passed,
            weight=6.0,
            score=score,
            critical=True,
            reason=(
                f"R:R={rr:.2f}"
            ),
        )

    # =====================================================
    # 20. STOP QUALITY
    # =====================================================

    def _check_stop_quality(
        self,
        signal: Dict[str, Any],
        direction: str,
        entry: float,
        stop_loss: float,
    ) -> Confirmation:

        if not self.config.require_stop_quality:

            return Confirmation(
                name="stop_quality",
                passed=True,
                weight=5.0,
                score=5.0,
                critical=False,
                reason="Stop-quality requirement disabled.",
            )

        stop_distance_percent = 0.0

        if entry > 0:

            stop_distance_percent = (
                abs(
                    entry
                    - stop_loss
                )
                / entry
                * 100.0
            )

        structure_valid = self._safe_bool(
            self._value(
                signal,
                "stop_structure_valid",
                "stop_valid",
                default=False,
            )
        )

        if direction == "LONG":

            direction_valid = (
                stop_loss < entry
            )

        else:

            direction_valid = (
                stop_loss > entry
            )

        passed = (
            direction_valid
            and stop_loss > 0
            and (
                structure_valid
                or structure_valid
                is False
            )
            and (
                stop_distance_percent
                > 0
            )
            and (
                stop_distance_percent
                <= 15.0
            )
        )

        return Confirmation(
            name="stop_quality",
            passed=passed,
            weight=5.0,
            score=(
                5.0
                if passed
                else 0.0
            ),
            critical=True,
            reason=(
                f"stop_distance="
                f"{stop_distance_percent:.3f}%, "
                f"structure_valid={structure_valid}"
            ),
        )

    # =====================================================
    # 21. POSITION SIZING
    # =====================================================

    def _check_position_size(
        self,
        entry: float,
        stop_loss: float,
    ) -> Confirmation:

        sizing = (
            self.calculate_quantity(
                entry_price=entry,
                stop_loss=stop_loss,
            )
        )

        passed = (
            sizing[
                "quantity"
            ] > 0
            and sizing[
                "risk_amount"
            ] > 0
            and sizing[
                "risk_amount"
            ]
            <= (
                self.balance
                * (
                    self.config.risk_per_trade_percent
                    / 100.0
                )
            )
            * 1.01
        )

        return Confirmation(
            name="position_sizing",
            passed=passed,
            weight=3.0,
            score=(
                3.0
                if passed
                else 0.0
            ),
            critical=True,
            reason=(
                f"quantity="
                f"{sizing['quantity']:.8f}, "
                f"risk="
                f"{sizing['risk_amount']:.4f}"
            ),
        )

    # =====================================================
    # 22. PORTFOLIO RISK
    # =====================================================

    def _check_portfolio_risk(
        self,
        signal: Dict[str, Any],
    ) -> Confirmation:

        if self._daily_loss_limit_reached():

            return Confirmation(
                name="portfolio_risk",
                passed=False,
                weight=4.0,
                score=0.0,
                critical=True,
                reason=(
                    "Daily loss limit reached."
                ),
            )

        if (
            len(self.positions)
            >= self.config.max_open_positions
        ):

            return Confirmation(
                name="portfolio_risk",
                passed=False,
                weight=4.0,
                score=0.0,
                critical=True,
                reason=(
                    "Maximum open positions reached."
                ),
            )

        symbol = self._normalize_symbol(
            self._value(
                signal,
                "symbol",
                "coin",
                default="",
            )
        )

        for position in self.positions.values():

            if (
                position.symbol
                == symbol
            ):

                return Confirmation(
                    name="portfolio_risk",
                    passed=False,
                    weight=4.0,
                    score=0.0,
                    critical=True,
                    reason=(
                        f"{symbol} already has "
                        "an open position."
                    ),
                )

        return Confirmation(
            name="portfolio_risk",
            passed=True,
            weight=4.0,
            score=4.0,
            critical=True,
            reason=(
                "Portfolio limits passed."
            ),
        )

    # =====================================================
    # 23. EXECUTION QUALITY
    # =====================================================

    def _check_execution_quality(
        self,
        signal: Dict[str, Any],
    ) -> Confirmation:

        execution_ok = self._safe_bool(
            self._value(
                signal,
                "execution_ok",
                default=True,
            ),
            default=True,
        )

        spread = self._safe_float(
            self._value(
                signal,
                "spread_percent",
                "spread_pct",
                default=0,
            )
        )

        slippage = self._safe_float(
            self._value(
                signal,
                "expected_slippage_percent",
                "slippage_percent",
                default=0,
            )
        )

        passed = (
            execution_ok
            and (
                spread
                <= self.config.max_spread_percent
            )
            and (
                slippage
                <= self.config.max_slippage_percent
            )
        )

        return Confirmation(
            name="execution_quality",
            passed=passed,
            weight=3.0,
            score=(
                3.0
                if passed
                else 0.0
            ),
            critical=True,
            reason=(
                f"execution_ok={execution_ok}, "
                f"spread={spread:.4f}%, "
                f"slippage={slippage:.4f}%"
            ),
        )

    # =====================================================
    # 24. SIGNAL FRESHNESS
    # =====================================================

    def _check_freshness(
        self,
        signal: Dict[str, Any],
    ) -> Confirmation:

        if not self.config.require_signal_freshness:

            return Confirmation(
                name="signal_freshness",
                passed=True,
                weight=3.0,
                score=3.0,
                critical=False,
                reason="Freshness check disabled.",
            )

        age = self._safe_float(
            self._value(
                signal,
                "signal_age_seconds",
                "age_seconds",
                default=0,
            )
        )

        timestamp = self._value(
            signal,
            "signal_timestamp",
            "timestamp",
            default=None,
        )

        # If no explicit age exists but a timestamp
        # exists, try to calculate it.
        if (
            age <= 0
            and timestamp
        ):

            try:

                parsed = (
                    datetime.fromisoformat(
                        str(
                            timestamp
                        ).replace(
                            "Z",
                            "+00:00",
                        )
                    )
                )

                if parsed.tzinfo is None:

                    parsed = parsed.replace(
                        tzinfo=timezone.utc
                    )

                age = (
                    datetime.now(
                        timezone.utc
                    )
                    - parsed
                ).total_seconds()

            except (
                ValueError,
                TypeError,
            ):

                age = 0

        passed = (
            age <=
            self.config.max_signal_age_seconds
        )

        return Confirmation(
            name="signal_freshness",
            passed=passed,
            weight=3.0,
            score=(
                3.0
                if passed
                else 0.0
            ),
            critical=True,
            reason=(
                f"age={age:.1f}s"
            ),
        )

    # =====================================================
    # ALL 24 CONFIRMATIONS
    # =====================================================

    def evaluate_confirmations(
        self,
        signal: Dict[str, Any],
    ) -> List[Confirmation]:

        direction = str(
            self._value(
                signal,
                "direction",
                default="NEUTRAL",
            )
            or "NEUTRAL"
        ).upper()

        entry = self._safe_float(
            self._value(
                signal,
                "entry",
                "entry_price",
                default=0,
            )
        )

        stop_loss = self._safe_float(
            self._value(
                signal,
                "stop_loss",
                "sl",
                default=0,
            )
        )

        return [
            self._check_market_regime(
                signal,
                direction,
            ),

            self._check_market_structure(
                signal,
                direction,
            ),

            self._check_multi_timeframe(
                signal,
                direction,
            ),

            self._check_entry_location(
                signal,
                direction,
            ),

            self._check_liquidity(
                signal,
                direction,
            ),

            self._check_vwap(
                signal,
                direction,
            ),

            self._check_volatility(
                signal,
            ),

            self._check_momentum(
                signal,
                direction,
            ),

            self._check_divergence(
                signal,
                direction,
            ),

            self._check_breakout(
                signal,
                direction,
            ),

            self._check_retest(
                signal,
            ),

            self._check_derivatives(
                signal,
                direction,
            ),

            self._check_liquidations(
                signal,
                direction,
            ),

            self._check_order_book(
                signal,
                direction,
            ),

            self._check_tradeability(
                signal,
            ),

            self._check_news(
                signal,
            ),

            self._check_market_context(
                signal,
                direction,
            ),

            self._check_relative_strength(
                signal,
                direction,
            ),

            self._check_risk_reward(
                signal,
            ),

            self._check_stop_quality(
                signal,
                direction,
                entry,
                stop_loss,
            ),

            self._check_position_size(
                entry,
                stop_loss,
            ),

            self._check_portfolio_risk(
                signal,
            ),

            self._check_execution_quality(
                signal,
            ),

            self._check_freshness(
                signal,
            ),
        ]

    # =====================================================
    # TRADE SCORE
    # =====================================================

    def calculate_trade_score(
        self,
        confirmations: List[Confirmation],
        signal: Dict[str, Any],
    ) -> Dict[str, Any]:

        total_weight = sum(
            item.weight
            for item in confirmations
        )

        total_score = sum(
            item.score
            for item in confirmations
        )

        if total_weight <= 0:

            raw_score = 0.0

        else:

            raw_score = (
                total_score
                / total_weight
                * 100.0
            )

        # Scanner confidence is used as an additional
        # independent quality input, but is never allowed
        # to overpower failed critical checks.

        scanner_confidence = self._safe_float(
            signal.get(
                "confidence",
                0,
            )
        )

        # Blend:
        # 75% rule-engine quality
        # 25% scanner confidence
        blended_score = (
            raw_score * 0.75
            + min(
                100.0,
                scanner_confidence,
            )
            * 0.25
        )

        critical_failures = [
            item.name
            for item in confirmations
            if (
                item.critical
                and not item.passed
            )
        ]

        passed_confirmations = sum(
            1
            for item in confirmations
            if item.passed
        )

        # Hard cap if critical checks fail.
        if critical_failures:

            blended_score = min(
                blended_score,
                89.9,
            )

        # Hard cap if too few independent confirmations.
        if (
            passed_confirmations
            < self.config.minimum_confirmations
        ):

            blended_score = min(
                blended_score,
                89.9,
            )

        # 100 is reserved for a completely clean gate.
        all_passed = all(
            item.passed
            for item in confirmations
        )

        if all_passed:

            blended_score = 100.0

        return {
            "raw_rule_score": round(
                raw_score,
                2,
            ),
            "scanner_confidence": round(
                scanner_confidence,
                2,
            ),
            "trade_score": round(
                min(
                    100.0,
                    blended_score,
                ),
                2,
            ),
            "passed_confirmations": (
                passed_confirmations
            ),
            "total_confirmations": len(
                confirmations
            ),
            "critical_failures": (
                critical_failures
            ),
            "all_checks_passed": (
                all_passed
            ),
        }

    # =====================================================
    # FINAL TRADE GATE
    # =====================================================

    def evaluate_trade(
        self,
        signal: Dict[str, Any],
    ) -> Dict[str, Any]:

        if not self.config.enabled:

            decision = {
                "decision": "NO_TRADE",
                "trade_score": 0.0,
                "reason": (
                    "Trade engine is disabled."
                ),
            }

            self.last_decision = decision

            return decision

        if not isinstance(
            signal,
            dict,
        ):

            decision = {
                "decision": "NO_TRADE",
                "trade_score": 0.0,
                "reason": (
                    "Invalid signal payload."
                ),
            }

            self.last_decision = decision

            return decision

        direction = str(
            signal.get(
                "direction",
                "NEUTRAL",
            )
            or "NEUTRAL"
        ).upper()

        symbol = self._normalize_symbol(
            signal.get(
                "symbol",
                signal.get(
                    "coin",
                    "",
                ),
            )
        )

        # Basic direction veto.
        if direction not in {
            "LONG",
            "SHORT",
        }:

            decision = {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "direction": direction,
                "trade_score": 0.0,
                "reason": (
                    "No valid LONG/SHORT direction."
                ),
            }

            self.last_decision = decision

            return decision

        if (
            direction == "LONG"
            and not self.config.allow_long
        ):

            decision = {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "direction": direction,
                "trade_score": 0.0,
                "reason": (
                    "LONG trading is disabled."
                ),
            }

            self.last_decision = decision

            return decision

        if (
            direction == "SHORT"
            and not self.config.allow_short
        ):

            decision = {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "direction": direction,
                "trade_score": 0.0,
                "reason": (
                    "SHORT trading is disabled."
                ),
            }

            self.last_decision = decision

            return decision

        confirmations = (
            self.evaluate_confirmations(
                signal
            )
        )

        score = (
            self.calculate_trade_score(
                confirmations,
                signal,
            )
        )

        trade_score = score[
            "trade_score"
        ]

        critical_failures = score[
            "critical_failures"
        ]

        passed_confirmations = score[
            "passed_confirmations"
        ]

        # -------------------------------------------------
        # HARD NO-TRADE
        # -------------------------------------------------

        if critical_failures:

            decision_name = (
                "NO_TRADE"
            )

        elif (
            passed_confirmations
            < self.config.minimum_confirmations
        ):

            decision_name = (
                "NO_TRADE"
            )

        elif (
            trade_score
            >= self.config.execute_threshold
        ):

            decision_name = (
                "EXECUTE_CANDIDATE"
            )

        elif (
            trade_score
            >= self.config.watch_threshold
        ):

            decision_name = (
                "WATCH"
            )

        else:

            decision_name = (
                "NO_TRADE"
            )

        reasons = [
            item.reason
            for item in confirmations
        ]

        decision = {
            "decision": decision_name,
            "symbol": symbol,
            "direction": direction,
            "trade_score": trade_score,
            "scanner_confidence": score[
                "scanner_confidence"
            ],
            "passed_confirmations": (
                passed_confirmations
            ),
            "total_confirmations": len(
                confirmations
            ),
            "critical_failures": (
                critical_failures
            ),
            "all_checks_passed": score[
                "all_checks_passed"
            ],
            "confirmations": [
                asdict(item)
                for item
                in confirmations
            ],
            "reasons": reasons,
            "timestamp": self._now(),
        }

        self.last_decision = decision

        return decision

    # =====================================================
    # POSITION SIZE
    # =====================================================

    def calculate_quantity(
        self,
        entry_price: float,
        stop_loss: float,
    ) -> Dict[str, float]:

        entry_price = self._safe_float(
            entry_price
        )

        stop_loss = self._safe_float(
            stop_loss
        )

        if (
            entry_price <= 0
            or stop_loss <= 0
        ):

            return {
                "risk_amount": 0.0,
                "stop_distance": 0.0,
                "stop_distance_percent": 0.0,
                "quantity": 0.0,
                "notional": 0.0,
            }

        risk_amount = (
            self._risk_amount()
        )

        stop_distance = abs(
            entry_price
            - stop_loss
        )

        if stop_distance <= 0:

            return {
                "risk_amount": 0.0,
                "stop_distance": 0.0,
                "stop_distance_percent": 0.0,
                "quantity": 0.0,
                "notional": 0.0,
            }

        quantity = (
            risk_amount
            / stop_distance
        )

        notional = (
            quantity
            * entry_price
        )

        stop_distance_percent = (
            stop_distance
            / entry_price
            * 100.0
        )

        return {
            "risk_amount": round(
                risk_amount,
                8,
            ),
            "stop_distance": round(
                stop_distance,
                8,
            ),
            "stop_distance_percent": round(
                stop_distance_percent,
                6,
            ),
            "quantity": round(
                quantity,
                8,
            ),
            "notional": round(
                notional,
                8,
            ),
        }

    # =====================================================
    # PAPER TRADE OPEN
    # =====================================================

    def open_paper_trade(
        self,
        signal: Dict[str, Any],
    ) -> Dict[str, Any]:

        decision = self.evaluate_trade(
            signal
        )

        if (
            decision.get(
                "decision"
            )
            != "EXECUTE_CANDIDATE"
        ):

            return {
                "success": False,
                "opened": False,
                "decision": decision,
                "reason": (
                    "Trade gate rejected "
                    "the signal."
                ),
            }

        symbol = decision[
            "symbol"
        ]

        direction = decision[
            "direction"
        ]

        confidence = self._safe_float(
            signal.get(
                "confidence",
                0,
            )
        )

        trade_score = self._safe_float(
            decision.get(
                "trade_score",
                0,
            )
        )

        entry = self._safe_float(
            self._value(
                signal,
                "entry",
                "entry_price",
                default=0,
            )
        )

        stop_loss = self._safe_float(
            self._value(
                signal,
                "stop_loss",
                "sl",
                default=0,
            )
        )

        tp1 = self._safe_float(
            self._value(
                signal,
                "tp1",
                default=0,
            )
        )

        tp2 = self._safe_float(
            self._value(
                signal,
                "tp2",
                default=0,
            )
        )

        tp3 = self._safe_float(
            self._value(
                signal,
                "tp3",
                default=0,
            )
        )

        sizing = (
            self.calculate_quantity(
                entry_price=entry,
                stop_loss=stop_loss,
            )
        )

        if (
            sizing["quantity"]
            <= 0
        ):

            return {
                "success": False,
                "opened": False,
                "decision": decision,
                "reason": (
                    "Position sizing failed."
                ),
            }

        position_id = (
            f"{symbol}-"
            f"{direction}-"
            f"{int(datetime.now().timestamp() * 1000)}"
        )

        position = PaperPosition(
            id=position_id,
            symbol=symbol,
            market=str(
                signal.get(
                    "market",
                    "futures",
                )
            ),
            direction=direction,
            entry_price=entry,
            quantity=sizing[
                "quantity"
            ],
            stop_loss=stop_loss,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            confidence=confidence,
            trade_score=trade_score,
            confirmations=decision[
                "passed_confirmations"
            ],
            risk_amount=sizing[
                "risk_amount"
            ],
            opened_at=self._now(),
        )

        self.positions[
            position_id
        ] = position

        self.last_signal = dict(
            signal
        )

        return {
            "success": True,
            "opened": True,
            "mode": "paper",
            "decision": decision,
            "position": asdict(
                position
            ),
            "sizing": sizing,
        }

    # =====================================================
    # POSITION UPDATE
    # =====================================================

    def update_position(
        self,
        position_id: str,
        current_price: float,
    ) -> Dict[str, Any]:

        position = self.positions.get(
            position_id
        )

        if position is None:

            return {
                "success": False,
                "reason": "Position not found.",
            }

        current_price = self._safe_float(
            current_price
        )

        if current_price <= 0:

            return {
                "success": False,
                "reason": "Invalid current price.",
            }

        # -------------------------------------------------
        # LONG
        # -------------------------------------------------

        if position.direction == "LONG":

            if (
                not position.tp1_hit
                and current_price
                >= position.tp1
            ):

                position.tp1_hit = True

            if (
                not position.tp2_hit
                and current_price
                >= position.tp2
            ):

                position.tp2_hit = True

            if (
                not position.tp3_hit
                and current_price
                >= position.tp3
            ):

                position.tp3_hit = True

                return self.close_position(
                    position_id,
                    current_price,
                    "TP3",
                )

            if (
                current_price
                <= position.stop_loss
            ):

                return self.close_position(
                    position_id,
                    current_price,
                    "STOP_LOSS",
                )

        # -------------------------------------------------
        # SHORT
        # -------------------------------------------------

        else:

            if (
                not position.tp1_hit
                and current_price
                <= position.tp1
            ):

                position.tp1_hit = True

            if (
                not position.tp2_hit
                and current_price
                <= position.tp2
            ):

                position.tp2_hit = True

            if (
                not position.tp3_hit
                and current_price
                <= position.tp3
            ):

                position.tp3_hit = True

                return self.close_position(
                    position_id,
                    current_price,
                    "TP3",
                )

            if (
                current_price
                >= position.stop_loss
            ):

                return self.close_position(
                    position_id,
                    current_price,
                    "STOP_LOSS",
                )

        return {
            "success": True,
            "closed": False,
            "position": asdict(
                position
            ),
        }

    # =====================================================
    # CLOSE
    # =====================================================

    def close_position(
        self,
        position_id: str,
        exit_price: float,
        reason: str = "MANUAL",
    ) -> Dict[str, Any]:

        position = self.positions.get(
            position_id
        )

        if position is None:

            return {
                "success": False,
                "reason": "Position not found.",
            }

        exit_price = self._safe_float(
            exit_price
        )

        if exit_price <= 0:

            return {
                "success": False,
                "reason": "Invalid exit price.",
            }

        if position.direction == "LONG":

            pnl = (
                exit_price
                - position.entry_price
            ) * position.quantity

        else:

            pnl = (
                position.entry_price
                - exit_price
            ) * position.quantity

        pnl = round(
            pnl,
            8,
        )

        position.realized_pnl = pnl

        position.status = "CLOSED"

        self.balance = round(
            self.balance + pnl,
            8,
        )

        self.daily_realized_pnl = round(
            self.daily_realized_pnl
            + pnl,
            8,
        )

        trade = asdict(
            position
        )

        trade[
            "exit_price"
        ] = exit_price

        trade[
            "close_reason"
        ] = reason

        trade[
            "closed_at"
        ] = self._now()

        self.closed_trades.append(
            trade
        )

        del self.positions[
            position_id
        ]

        return {
            "success": True,
            "closed": True,
            "pnl": pnl,
            "balance": (
                self.get_balance()
            ),
            "trade": trade,
        }

    # =====================================================
    # DAILY RESET
    # =====================================================

    def reset_daily_stats(
        self,
    ) -> Dict[str, Any]:

        self.daily_realized_pnl = 0.0

        return {
            "success": True,
            "daily_realized_pnl": 0.0,
            "daily_loss_percent": 0.0,
        }


# =========================================================
# DEFAULT ENGINE
# =========================================================

default_trade_engine = TradeEngine(
    starting_balance=1000.0,
    config=TradeConfig(
        enabled=True,
        mode="paper",
        execute_threshold=95.0,
        watch_threshold=90.0,
        minimum_confirmations=8,
        risk_per_trade_percent=0.5,
        max_open_positions=2,
        max_daily_loss_percent=2.0,
        minimum_risk_reward=1.5,
        max_spread_percent=0.15,
        max_slippage_percent=0.20,
        max_signal_age_seconds=120,
        allow_long=True,
        allow_short=True,
        require_news_check=False,
        require_market_context=True,
        require_entry_location=True,
        require_stop_quality=True,
        require_risk_reward=True,
        require_signal_freshness=True,
    ),
)


__all__ = [
    "TradeConfig",
    "PaperPosition",
    "Confirmation",
    "TradeEngine",
    "default_trade_engine",
]

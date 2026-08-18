const API_BASE = "/api";


async function request(
    path,
    options = {}
) {
    const response = await fetch(
        `${API_BASE}${path}`,
        {
            headers: {
                "Content-Type":
                    "application/json",
                ...(options.headers || {})
            },
            ...options
        }
    );


    let data = null;

    try {
        data = await response.json();
    } catch (error) {
        data = {
            success: false,
            error: "Invalid server response."
        };
    }


    if (!response.ok) {

        throw new Error(
            data?.error
            || data?.detail
            || `HTTP ${response.status}`
        );
    }


    return data;
}


// =====================================================
// SYSTEM
// =====================================================

async function health() {

    return request(
        "/health"
    );
}


async function markets() {

    return request(
        "/markets"
    );
}


// =====================================================
// MARKET SEARCH
// =====================================================

async function search(
    query,
    market = "futures"
) {

    const params =
        new URLSearchParams({
            q: String(
                query || ""
            ),
            market
        });

    return request(
        `/search?${params.toString()}`
    );
}


// =====================================================
// ANALYSIS
// =====================================================

async function analyze(
    symbol,
    market = "futures"
) {

    const params =
        new URLSearchParams({
            symbol: String(
                symbol || ""
            ),
            market
        });

    return request(
        `/analyze?${params.toString()}`
    );
}


// =====================================================
// SCANNER
// =====================================================

async function scan(
    market = "futures"
) {

    const params =
        new URLSearchParams({
            market
        });

    return request(
        `/scan?${params.toString()}`
    );
}


// =====================================================
// SIGNALS
// =====================================================

async function signals() {

    return request(
        "/signals"
    );
}


// =====================================================
// TRADE ENGINE
// =====================================================

async function tradeStatus() {

    return request(
        "/trade/status"
    );
}


async function positions() {

    return request(
        "/trade/positions"
    );
}


async function tradeHistory() {

    return request(
        "/trade/history"
    );
}


async function evaluateTrade(
    signal
) {

    return request(
        "/trade/evaluate",
        {
            method: "POST",
            body: JSON.stringify(
                signal
            )
        }
    );
}


async function openPaperTrade(
    signal
) {

    return request(
        "/trade/paper/open",
        {
            method: "POST",
            body: JSON.stringify(
                signal
            )
        }
    );
}


async function resetDailyRisk() {

    return request(
        "/trade/reset-daily",
        {
            method: "POST"
        }
    );
}


// =====================================================
// EXPORT
// =====================================================

export {
    health,
    markets,
    search,
    analyze,
    scan,
    signals,
    tradeStatus,
    positions,
    tradeHistory,
    evaluateTrade,
    openPaperTrade,
    resetDailyRisk
};

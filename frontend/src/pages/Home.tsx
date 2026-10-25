import { Link, useNavigate } from "react-router-dom";
import { Arrow, SearchBox } from "../components";
import { useRecents } from "../storage";

function AskMock() {
  return (
    <div className="mock">
      <div className="mock-head"><strong>Ask</strong><span>Apple Inc.</span></div>
      <div className="mock-body">
        <div className="q">What are the main supply chain risks?</div>
        <div className="a">Component shortages could reduce gross margin <span className="cite static">1</span></div>
        <div className="src"><b>10-K · Item 1A. Risk Factors · Page 12</b><br />“…<mark>Component shortages could reduce our gross margin</mark>…”</div>
      </div>
      <div className="mock-note">Sample output</div>
    </div>
  );
}

function SnapshotMock() {
  return (
    <div className="mock">
      <div className="mock-head"><strong>Apple Inc.</strong><span>FY2024</span></div>
      <div className="mock-body">
        <div className="kv">
          <span>Revenue</span><span className="num">$391.0B</span>
          <span>Net income</span><span className="num">$93.7B</span>
          <span>Net margin</span><span className="num">24.0%</span>
        </div>
        <div className="code" style={{ marginTop: 12 }}>us-gaap:Revenues · SEC XBRL</div>
      </div>
      <div className="mock-note">Sample output</div>
    </div>
  );
}

function FactsVisual() {
  const rows = [["Revenue", "$391.0B", "Revenues"], ["Net income", "$93.7B", "NetIncomeLoss"], ["Total assets", "$365.0B", "Assets"]];
  return (
    <div className="visual">
      <div className="mock">
        <div className="mock-head"><strong>Income statement and balance sheet</strong><span>FY2024</span></div>
        <table className="table">
          <thead><tr><th>Item</th><th className="r">Value</th><th>Source tag</th></tr></thead>
          <tbody>{rows.map((r) => <tr key={r[0]}><td className="k">{r[0]}</td><td className="r num">{r[1]}</td><td className="code">{r[2]}</td></tr>)}</tbody>
        </table>
        <div className="mock-note">Sample output</div>
      </div>
    </div>
  );
}

function CiteVisual() {
  return (
    <div className="visual">
      <div className="mock">
        <div className="mock-body">
          <div className="a">Component shortages could reduce gross margin <span className="cite static">1</span></div>
          <div className="src" style={{ background: "var(--wash)" }}>
            <b>10-K · Item 1A. Risk Factors · Page 12</b>
            <p style={{ marginTop: 6 }}>Our business depends on global supply chains. <mark>Component shortages could reduce our gross margin.</mark> We rely on a limited number of suppliers.</p>
          </div>
          <div className="muted" style={{ marginTop: 12, fontSize: 13 }}>1 unsupported sentence removed</div>
        </div>
        <div className="mock-note">Sample output</div>
      </div>
    </div>
  );
}

function ReportsVisual() {
  return (
    <div className="visual">
      <div className="mock">
        <div className="mock-head"><strong>Annual reports</strong><span>NSE</span></div>
        <table className="table">
          <tbody>
            <tr><td className="k">FY 2023-24</td><td><span className="badge good">Searchable</span></td><td className="r"></td></tr>
            <tr><td className="k">FY 2022-23</td><td><span className="badge">Not downloaded</span></td><td className="r"><span className="btn sm" aria-hidden>Make searchable</span></td></tr>
          </tbody>
        </table>
        <div className="mock-note">Sample output</div>
      </div>
    </div>
  );
}

export default function Home() {
  const nav = useNavigate();
  const recents = useRecents().list;
  const quick = recents.length ? recents.slice(0, 5) : ["AAPL", "MSFT", "NVDA", "RELIANCE"];
  return (
    <>
      <section className="hero">
        <div className="hero-band" aria-hidden />
        <div className="wrap">
          <div>
            <h1>Annual reports, with the sources attached.</h1>
            <p className="lede">
              Look up a company, read its reported numbers, and ask questions about its filings. Every figure and every
              answer points back to the document it came from.
            </p>
            <SearchBox autoFocus />
            <div className="hero-links">
              <span>{recents.length ? "Recent" : "Try"}</span>
              {quick.map((t) => <button key={t} onClick={() => nav(`/company/${t}`)}>{t}</button>)}
            </div>
          </div>
          <div className="stack" aria-hidden>
            <div className="m1"><AskMock /></div>
            <div className="m2"><SnapshotMock /></div>
          </div>
        </div>
      </section>

      <section className="dark-band">
        <div className="wrap">
          <h2>Every answer is built in four separate steps.</h2>
          <p className="intro">Keeping the steps apart means you can check each one. A model only ever explains what the earlier steps found.</p>
          <div className="flow">
            <div><span className="n">1</span><h3>Sources</h3><p>Filings and market feeds provide the facts. Each number keeps the tag it was reported under.</p></div>
            <div><span className="n">2</span><h3>Calculation</h3><p>Margins and returns are computed in code from reported figures, so the same inputs give the same result.</p></div>
            <div><span className="n">3</span><h3>Retrieval</h3><p>Search selects the passages that matter, with their section and page number.</p></div>
            <div><span className="n">4</span><h3>Explanation</h3><p>A model writes a short answer from those passages only. Code then removes anything they don't support.</p></div>
          </div>
        </div>
      </section>

      <section className="feature">
        <div className="wrap">
          <div className="copy">
            <h2>Reported numbers, with their source.</h2>
            <p>Revenue, profit, assets and cash flow come straight from SEC filings. See the tag behind each value, follow five years of trends, and export what you see to CSV.</p>
            <Link className="more" to="/company/AAPL">Open a company <Arrow /></Link>
          </div>
          <FactsVisual />
        </div>
      </section>

      <section className="feature rev">
        <div className="wrap">
          <div className="copy">
            <h2>Ask a question, then check the page.</h2>
            <p>Each answer links to the passage behind it. Open a citation to read the sentence in the filing, highlighted, with a link to the original document.</p>
            <Link className="more" to="/company/AAPL">Try it on a company <Arrow /></Link>
          </div>
          <CiteVisual />
        </div>
      </section>

      <section className="feature">
        <div className="wrap">
          <div className="copy">
            <h2>US and Indian companies in one place.</h2>
            <p>Read NSE annual reports the same way as a 10-K, compare up to four US companies on the same fiscal year, and follow prices on a watchlist.</p>
            <Link className="more" to="/compare">Compare companies <Arrow /></Link>
          </div>
          <ReportsVisual />
        </div>
      </section>

      <section className="cta">
        <div className="wrap">
          <h2>Look up a company to get started.</h2>
          <SearchBox placeholder="Search a ticker" />
        </div>
      </section>
    </>
  );
}

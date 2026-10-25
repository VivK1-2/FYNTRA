import { Link, NavLink, Route, Routes } from "react-router-dom";
import { Logo, SearchBox } from "./components";
import { useTheme } from "./storage";
import Home from "./pages/Home";
import CompanyPage from "./pages/Company";
import Compare from "./pages/Compare";
import Markets from "./pages/Markets";
import Admin from "./pages/Admin";

function Nav() {
  const [theme, toggle] = useTheme();
  return (
    <header className="nav">
      <div className="wrap">
        <Link to="/" className="brand"><Logo />FYNTRA</Link>
        <nav className="nav-links" aria-label="Main">
          <NavLink to="/markets">Markets</NavLink>
          <NavLink to="/compare">Compare</NavLink>
        </nav>
        <div className="nav-right">
          <SearchBox className="nav-search" button={false} placeholder="Search a ticker" />
          <button className="icon-btn" onClick={toggle} aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"} title="Theme">
            {theme === "dark"
              ? <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
              : <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"><path d="M20 14.5A8 8 0 019.5 4 8 8 0 1020 14.5z" /></svg>}
          </button>
        </div>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer>
      <div className="wrap">
        <div className="foot">
          <div>
            <Link to="/" className="brand"><Logo />FYNTRA</Link>
            <p style={{ marginTop: 14, maxWidth: "22em" }}>Financial Year Narratives, Tables, Ratios &amp; Answers: annual reports and financials with the sources attached. Runs on your own computer.</p>
          </div>
          <div><h4>Explore</h4><ul><li><Link to="/markets">Markets</Link></li><li><Link to="/compare">Compare</Link></li><li><Link to="/admin">Admin</Link></li></ul></div>
          <div><h4>Data from</h4><ul><li>SEC EDGAR</li><li>NSE India</li><li>Yahoo Finance</li></ul></div>
          <div><h4>How it works</h4><ul><li>Figures are reported by the filer</li><li>Ratios are calculated in code</li><li>Answers cite the report page</li></ul></div>
        </div>
        <div className="legal"><span>© FYNTRA</span><span>For information only, not investment advice.</span></div>
      </div>
    </footer>
  );
}

export default function App() {
  return (
    <>
      <Nav />
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/company/:id" element={<CompanyPage />} />
          <Route path="/markets" element={<Markets />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="*" element={<div className="wrap body"><h1>Page not found</h1><p style={{ marginTop: 10 }}><Link to="/">Back to home</Link></p></div>} />
        </Routes>
      </main>
      <Footer />
    </>
  );
}

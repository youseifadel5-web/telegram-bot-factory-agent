import { useEffect, useMemo, useState } from "react";
import {
  Bookmark,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Compass,
  Flame,
  Grid2X2,
  Heart,
  Home as HomeIcon,
  Play,
  Search,
  Send,
  SlidersHorizontal,
  Star,
  Ticket,
  UserRound,
  X,
} from "lucide-react";

const movies = [
  { id: 1, title: "The Last Horizon", arabic: "الأفق الأخير", year: "2025", genre: "خيال علمي", quality: "4K", poster: "https://images.unsplash.com/photo-1536440136628-849c177e76a1?auto=format&fit=crop&w=700&q=85", tone: "violet" },
  { id: 2, title: "Midnight Protocol", arabic: "بروتوكول منتصف الليل", year: "2024", genre: "إثارة", quality: "1080p", poster: "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?auto=format&fit=crop&w=700&q=85", tone: "blue" },
  { id: 3, title: "Wild Kingdom", arabic: "المملكة البرية", year: "2025", genre: "وثائقي", quality: "4K", poster: "https://images.unsplash.com/photo-1511497584788-876760111969?auto=format&fit=crop&w=700&q=85", tone: "green" },
  { id: 4, title: "Echoes of Rome", arabic: "أصداء روما", year: "2023", genre: "دراما", quality: "1080p", poster: "https://images.unsplash.com/photo-1528181304800-259b08848526?auto=format&fit=crop&w=700&q=85", tone: "amber" },
  { id: 5, title: "The Silent Code", arabic: "الشيفرة الصامتة", year: "2024", genre: "جريمة", quality: "1080p", poster: "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?auto=format&fit=crop&w=700&q=85", tone: "red" },
  { id: 6, title: "Blue Hour", arabic: "الساعة الزرقاء", year: "2025", genre: "رومانسي", quality: "720p", poster: "https://images.unsplash.com/photo-1500534623283-312aade485b7?auto=format&fit=crop&w=700&q=85", tone: "cyan" },
];

const categories = ["الكل", "أفلام", "مسلسلات", "أنمي", "وثائقي", "أكشن", "رعب", "كوميديا"];
const castById: Record<number, string[]> = { 1: ["جيمس هاربر", "ليلى موران"], 2: ["آدم كول", "سارة نوفاك"], 3: ["رايلي ستون", "نورا كين"], 4: ["مريم حداد", "إياد منصور"], 5: ["كريم سالم", "هانا لو"], 6: ["نور عادل", "يوسف جابر"] };

function MovieCard({ movie, onOpen }: { movie: (typeof movies)[number]; onOpen: () => void }) {
  return (
    <button className="movie-card" onClick={onOpen} aria-label={`عرض تفاصيل ${movie.arabic}`}>
      <div className={`poster poster-${movie.tone}`} style={{ backgroundImage: `url(${movie.poster})` }}>
        <div className="poster-shade" />
        <span className="quality-badge">{movie.quality}</span>
        <span className="play-circle"><Play size={16} fill="currentColor" /></span>
      </div>
      <div className="movie-card-copy">
        <strong>{movie.arabic}</strong>
        <span>{movie.year} · {movie.genre}</span>
      </div>
    </button>
  );
}

export default function Home() {
  const [activeCategory, setActiveCategory] = useState("الكل");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<(typeof movies)[number] | null>(null);
  const [saved, setSaved] = useState<number[]>([]);
  const [remoteMovies, setRemoteMovies] = useState<any[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [searchState, setSearchState] = useState<"idle" | "loading" | "error">("idle");
  const [page, setPage] = useState(1);
  const [retryNonce, setRetryNonce] = useState(0);

  useEffect(() => {
    const value = query.trim();
    if (!value) { setRemoteMovies([]); setSuggestions([]); setSearchState("idle"); setPage(1); return; }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setSearchState("loading");
      try {
        const response = await fetch(`/api/movies/search?q=${encodeURIComponent(value)}&page=${page}`, { signal: controller.signal });
        if (!response.ok) throw new Error("search failed");
        const data = await response.json();
        setRemoteMovies(Array.isArray(data.movies) ? data.movies : []);
        setSuggestions(Array.isArray(data.suggestions) ? data.suggestions : []);
        setSearchState("idle");
      } catch (error) {
        if (!controller.signal.aborted) setSearchState("error");
      }
    }, 350);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [query, page, retryNonce]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const source = query.trim() && searchState !== "error" ? remoteMovies : movies;
    return source.filter((movie: any) => {
      const matchesQuery = !normalized || `${movie.arabic} ${movie.title} ${movie.genre}`.toLowerCase().includes(normalized);
      const matchesCategory = activeCategory === "الكل" || movie.genre === activeCategory || (activeCategory === "أفلام" && movie.id % 2 === 1);
      return matchesQuery && matchesCategory;
    });
  }, [activeCategory, query]);

  return (
    <div className="app-shell" dir="rtl">
      <header className="topbar">
        <div className="brand-lockup"><div className="brand-mark"><Ticket size={19} /></div><div><strong>Movie<span>VIP</span></strong><small>عالمك السينمائي</small></div></div>
        <div className="top-actions"><button className="icon-button"><BellDot /></button><button className="avatar"><UserRound size={18} /></button></div>
      </header>

      <main className="page-content">
        <section className="hero-banner">
          <div className="hero-glow" />
          <div className="hero-copy"><span className="eyebrow"><Flame size={14} fill="currentColor" /> الأكثر مشاهدة هذا الأسبوع</span><h1>قصص لا تُنسى،<br /><em>في كل مشاهدة.</em></h1><p>اكتشف أحدث الأفلام والمسلسلات بجودات متعددة، في مكان واحد.</p><button className="primary-button" onClick={() => setSelected(movies[0])}><Play size={16} fill="currentColor" /> ابدأ المشاهدة</button></div>
          <div className="hero-art"><div className="hero-orbit orbit-one" /><div className="hero-orbit orbit-two" /><div className="hero-number">01</div><div className="hero-meta"><span>THE LAST HORIZON</span><small>مغامرة · خيال علمي · 2025</small></div></div>
        </section>

        <section className="search-row"><div className="search-box"><Search size={18} /><input aria-label="البحث عن فيلم أو مسلسل" value={query} onChange={(e) => { setQuery(e.target.value); setPage(1); }} placeholder="ابحث عن فيلم، مسلسل أو ممثل..." /><kbd>⌘ K</kbd></div><button className="filter-button" aria-label="فتح التصفية"><SlidersHorizontal size={18} /> <span>تصفية</span></button></section>{query.trim() && suggestions.length > 0 && <div className="suggestions-row" aria-label="اقتراحات البحث">{suggestions.map((suggestion) => <button key={suggestion} onClick={() => { setQuery(suggestion); setPage(1); }}>{suggestion}</button>)}</div>}{searchState === "loading" && <div className="search-status">جاري البحث...</div>}{searchState === "error" && <div className="search-error">تعذر الاتصال بالمصدر. <button onClick={() => { setSearchState("loading"); setRetryNonce((value) => value + 1); }}>إعادة المحاولة</button></div>}

        <div className="category-row">{categories.map((category) => <button key={category} className={activeCategory === category ? "category active" : "category"} onClick={() => setActiveCategory(category)}>{category}</button>)}</div>

        <section className="section-block"><div className="section-heading"><div><span className="section-kicker">مختارات اليوم</span><h2>الأكثر مشاهدة الآن</h2></div><button className="text-link">عرض الكل <ChevronLeft size={16} /></button></div>{filtered.length ? <div className="movie-grid">{filtered.slice(0, 4).map((movie) => <MovieCard movie={movie} key={movie.id} onOpen={() => setSelected(movie)} />)}</div> : <div className="empty-state"><Search size={24} /><strong>لم نجد نتائج مطابقة</strong><span>جرّب كلمة بحث مختلفة أو استكشف التصنيفات.</span></div>}</section>

        <section className="wide-promo"><div><span className="section-kicker">تجربة مشاهدة أفضل</span><h2>جودة عالية.<br /><span>بدون تعقيد.</span></h2><p>اختر الجودة التي تناسب اتصالك واستمتع بتجربة سلسة.</p><button className="outline-button">استكشف الجودات <ChevronLeft size={16} /></button></div><div className="quality-stack"><div className="quality-tile back">720p</div><div className="quality-tile mid">1080p</div><div className="quality-tile front"><strong>4K</strong><small>Ultra HD</small></div></div></section>

        <section className="section-block"><div className="section-heading"><div><span className="section-kicker">تصفح حسب ذوقك</span><h2>وصل حديثاً</h2></div><div className="arrows"><button aria-label="السابق" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}><ChevronRight size={18} /></button><button aria-label="التالي" onClick={() => setPage((value) => value + 1)}><ChevronLeft size={18} /></button></div></div><div className="movie-grid">{filtered.slice(4).map((movie) => <MovieCard movie={movie} key={movie.id} onOpen={() => setSelected(movie)} />)}</div></section>

        <section className="section-block"><div className="section-heading"><div><span className="section-kicker">اختيارات تناسبك</span><h2>ربما يعجبك أيضاً</h2></div><button className="text-link">تحديث <ChevronLeft size={16} /></button></div><div className="movie-grid">{movies.slice(2, 6).map((movie) => <MovieCard movie={movie} key={`recommend-${movie.id}`} onOpen={() => setSelected(movie)} />)}</div></section>
      </main>

      <nav className="bottom-nav"><button className="nav-item active"><HomeIcon size={19} /><span>الرئيسية</span></button><button className="nav-item"><Compass size={19} /><span>اكتشف</span></button><button className="nav-item center"><span><Play size={21} fill="currentColor" /></span><small>شاهد الآن</small></button><button className="nav-item"><Bookmark size={19} /><span>قائمتي</span></button><button className="nav-item"><Grid2X2 size={19} /><span>المزيد</span></button></nav>

      {selected && <div className="modal-backdrop" onClick={() => setSelected(null)}><div className="detail-sheet" onClick={(e) => e.stopPropagation()}><button className="close-button" onClick={() => setSelected(null)}><X size={19} /></button><div className="detail-poster" style={{ backgroundImage: `url(${selected.poster})` }}><div className="poster-shade" /><span className="detail-play"><Play size={20} fill="currentColor" /></span></div><div className="detail-copy"><span className="section-kicker">تفاصيل الفيلم</span><h2>{selected.arabic}</h2><p className="latin-title">{selected.title}</p><div className="detail-meta"><span><Star size={14} fill="currentColor" /> 2025</span><span><Clock3 size={14} /> 02:08</span><span>{selected.genre}</span></div><p>رحلة سينمائية ممتعة بتفاصيل بصرية غنية وقصة تأخذك إلى عالم مختلف.</p><div className="cast-line"><strong>طاقم العمل</strong><span>{(castById[selected.id] ?? []).join(" · ")}</span></div><div className="quality-options"><button className="selected-quality">4K <small>الأفضل</small></button><button>1080p</button><button>720p</button></div><button className="primary-button full" onClick={async () => { const response = await fetch(`/api/movies/${selected.id}/play`); const data = await response.json(); if (typeof data.url === "string" && (data.url.startsWith("https://") || data.url.startsWith("http://"))) window.open(data.url, "_blank", "noopener,noreferrer"); }}>{<Play size={17} fill="currentColor" />} شاهد الآن</button><button className="outline-button full" onClick={() => setSaved((items) => items.includes(selected.id) ? items.filter((id) => id !== selected.id) : [...items, selected.id])}>{saved.includes(selected.id) ? <Heart size={16} fill="currentColor" /> : <Bookmark size={16} />} {saved.includes(selected.id) ? "تمت الإضافة لقائمتي" : "أضف إلى قائمتي"}</button></div></div></div>}
    </div>
  );
}

function BellDot() { return <span className="bell-dot"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg><i /></span>; }

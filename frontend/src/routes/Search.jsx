import { useState, useEffect } from "react";
import { apiFetch } from "@/hooks/useApi";
import SpaceSelect  from "@/components/SpaceSelect";


export default function Search() {
  const [q, setQ]           = useState("");
  const [_spaces, setSpaces] = useState([]);
  const [space, setSpace]   = useState("");
  const [results, setResults] = useState([]);
  const [searched, setSearched] = useState(false);
  useEffect(() => {
    apiFetch("user/spaces").then((d) => {
      const s = d.spaces || [];
      setSpaces(s);
      if (s.length > 0) setSpace(s[0]);
    }).catch((e) => console.error("Failed to fetch spaces", e));
  }, []);

  const [loading, setLoading] = useState(false);
  const [feedbackById, setFeedbackById] = useState({});
  const [toast, setToast] = useState({ docId: null, msg: "" });

  // Highlight helper
  const renderSnippet = (snippet) => {
    const terms = Array.from(
      new Set(
        q
          .toLowerCase()
          .normalize("NFD")
          .replace(/[\u0300-\u036f]/g, "")
          .split(/[^A-Za-z]+/)
          .filter(Boolean)
      )
    );
    return snippet.split(" ").map((word, i) => {
      const ascii = word
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "");
      const clean = ascii.replace(/[^A-Za-z]/g, "").toLowerCase();
      if (terms.includes(clean)) {
        return (
          <strong key={i} className="font-bold">
            {word}{" "}
          </strong>
        );
      }
      return <span key={i}>{word} </span>;
    });
  };

  const onSearch = async () => {
    if (!q.trim()) return;
    setLoading(true);
    setSearched(true);
    try {
      const res = await apiFetch(
        "search",
        `?q=${encodeURIComponent(q)}&space=${space}`
      );
      setResults(res.results || []);
    } catch (err) {
      console.error("Search error:", err);
      alert("Search failed. Check console.");
    } finally {
      setLoading(false);
    }
  };

  const sendFeedback = async (docId, positive) => {
    // stub: you'll wire this up to /feedback later
    setFeedbackById((f) => ({ ...f, [docId]: positive }));
    setToast({ docId, msg: positive ? "Gracias por su feedback!" : "Gracias, vamos a mejorar!" });
    setTimeout(() => setToast({ docId: null, msg: "" }), 2000);
  };

  return (
    <div className="w-full flex-1 overflow-y-auto min-h-0 space-y-4 px-16 py-8">
      <h2 className="text-2xl font-semibold mb-4">Buscar documentos</h2>

      <div className="flex items-center mb-6 space-x-4">
        <SpaceSelect
          value={space}
          onChange={(v) => setSpace(v)}
            className="focus:outline-none" 
          // className="h-11 px-4 bg-transparent transition rounded-2xl hover:bg-gray-50 hover:cursor-pointer focus:outline-none ring-0 focus-visible:ring-0 [aria-expanded=true]:ring-0 border border-transparent hover:border-inherit"
        />
        <div className={`input-wrapper flex-grow relative ${q ? 'caret-hidden' : ''}`}>
          <input
            type="text"
            className="flex-grow w-full py-3 px-4 border rounded-2xl
                              focus:outline-none focus:placeholder-transparent
                              hover:bg-gray-50 transition-colors"
            placeholder="Ingresa las palabras de tu busqueda..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onSearch()}
          />
        </div>
        <button
          onClick={onSearch}
          className="px-8 py-3 bg-gray-200 text-gray-900 rounded-3xl hover:bg-gray-300 transition"
          disabled={loading}
        >
          {loading ? "Buscando..." : "Buscar"}
        </button>
      </div>

      <ul className="space-y-4">

        {/* ---------- 1) empty state ---------- */}
        {searched && !loading && results.length === 0 && (
          <li className="text-gray-500 italic px-2">
            No se encontraron resultados.
          </li>
        )}

        {/* ---------- 2) actual hits ---------- */}
        {results.map((res) => {
          const fb = feedbackById[res.id];
          const isToast = toast.docId === res.id;

          return (
            <li
              key={res.id}
              className="p-4 border rounded-lg hover:shadow flex flex-col"
            >
              <div className="relative">
                <div className="flex justify-between items-center">
                  <h3 className="text-lg font-semibold">{res.title}</h3>
                  <span className="text-sm font-mono text-gray-500">
                    ID: {res.id}
                  </span>
                </div>
                <span className="text-sm font-semibold text-indigo-600">
                  Score: {res.score.toFixed(3)}
                </span>

                <p className="mt-2 text-gray-700 text-sm">
                  {renderSnippet(res.snippet)}
                  {res.snippet.split(" ").length >= 50 ? "…" : ""}
                </p>

                <div className="mt-3 flex items-center space-x-2">
                  {res.download_url && (
                    <a
                    href={res.download_url}
                    target="_blank"
                      rel="noreferrer"
                      className="px-4 py-2 bg-gray-200 rounded hover:bg-gray-100"
                      >
                      Descargar documento completo
                    </a>
                  )}
                  <div className="absolute bottom-2 right-2 flex space-x-2">
                    <button
                      onClick={() => sendFeedback(res.id, true)}
                      disabled={fb != null}
                      className={`p-1 rounded-full transition ${
                        fb === true ? "bg-green-200 text-green-800" : "hover:bg-green-100 text-gray-600"
                      }`}
                      >
                      👍
                    </button>
                    <button
                      onClick={() => sendFeedback(res.id, false)}
                      disabled={fb != null}
                      className={`p-1 rounded-full transition ${
                        fb === false ? "bg-red-200 text-red-800" : "hover:bg-red-100 text-gray-600"
                      }`}
                      >
                      👎
                    </button>
                  </div>
                </div>

                {isToast && (
                  <div
                    className="
                      absolute 
                      bottom-10 right-2      /* position above the buttons */
                      bg-white border border-gray-300
                      text-gray-800
                      px-3 py-1
                      rounded-md shadow-lg
                      animate-fade-in-out z-10
                    "
                  >
                    {toast.msg}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

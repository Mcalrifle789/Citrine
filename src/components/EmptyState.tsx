import wordmark from '../assets/wordmark.png'

const SUGGESTIONS: Array<[string, string]> = [
  ['chat', 'Start an interactive AI chat'],
  ['code', 'Generate code from a description'],
  ['explain', 'Explain a block of code'],
  ['test', 'Generate tests for your code'],
  ['docs', 'Generate documentation'],
  ['init', 'Initialize a new project'],
]

/** The application's face on launch — the mockup's welcome screen. */
export function EmptyState() {
  return (
    <div className="ct-empty">
      <img className="ct-empty__wordmark" src={wordmark} alt="Citrine" />
      <p className="ct-empty__tagline">-- AI-Powered Development Assistant</p>
      <hr className="ct-empty__rule" />
      <p>
        Welcome to <span className="ct-accent">Citrine</span>! How can I help you build
        something amazing today?
      </p>
      <p>Try one of these commands to get started:</p>
      <ul className="ct-empty__list">
        {SUGGESTIONS.map(([name, description]) => (
          <li key={name}>
            <span className="ct-empty__star" aria-hidden="true">
              ✷
            </span>
            <span className="ct-empty__cmd">{name}</span>
            <span className="ct-empty__desc">{description}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

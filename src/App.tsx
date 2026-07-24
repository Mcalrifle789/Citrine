import wordmark from './assets/wordmark.png'

/**
 * Placeholder shell. Task 4 introduces the terminal primitives and Task 9
 * assembles the real layout; for now this exists to prove the backdrop and
 * wordmark render.
 */
export function App() {
  return (
    <>
      <div className="citrine-backdrop" aria-hidden="true" />
      <div className="citrine-splash">
        <img className="citrine-wordmark" src={wordmark} alt="Citrine" />
      </div>
    </>
  )
}

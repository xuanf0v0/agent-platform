import Dashboard from './components/Dashboard';
import ParticleField from './components/ParticleField';

export default function App() {
  return (
    <main className="app-shell">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <ParticleField />
      <svg className="network" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <g className="network-lines">
          <path d="M50 220 240 110 420 260 630 130 820 280 1030 120 1260 250 1410 100" />
          <path d="M-30 620 190 470 390 650 620 430 830 640 1060 410 1280 590 1490 430" />
          <path d="M240 110 190 470M420 260 390 650M630 130 620 430M820 280 830 640M1030 120 1060 410M1260 250 1280 590" />
        </g>
        <g className="network-nodes">
          {[['50','220'],['240','110'],['420','260'],['630','130'],['820','280'],['1030','120'],['1260','250'],['190','470'],['390','650'],['620','430'],['830','640'],['1060','410'],['1280','590']].map(([cx, cy]) => (
            <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="3" />
          ))}
        </g>
      </svg>
      <div className="app-content">
        <Dashboard />
      </div>
    </main>
  );
}

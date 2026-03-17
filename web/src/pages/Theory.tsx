import { Routes, Route } from 'react-router-dom';
import { TheorySidebar } from '../components/theory/TheorySidebar';
import { TheoryLanding } from '../components/theory/TheoryLanding';
import { DocViewer } from '../components/theory/DocViewer';
import './Theory.css';

export function Theory() {
  return (
    <div className="theory-page container">
      <TheorySidebar />
      <main className="theory-content">
        <Routes>
          <Route index element={<TheoryLanding />} />
          <Route path=":category/:slug" element={<DocViewer />} />
        </Routes>
      </main>
    </div>
  );
}

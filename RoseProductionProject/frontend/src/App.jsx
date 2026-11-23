import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout.jsx';
import { ErrorState, LoadingState } from './components/States.jsx';
import { useAuth } from './context/AuthContext.jsx';
import Analytics from './pages/Analytics.jsx';
import Crops from './pages/Crops.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Farms from './pages/Farms.jsx';
import Forecasts from './pages/Forecasts.jsx';
import Harvests from './pages/Harvests.jsx';
import Login from './pages/Login.jsx';
import Lots from './pages/Lots.jsx';
import Seasons from './pages/Seasons.jsx';
import Varieties from './pages/Varieties.jsx';

export default function App() {
  const { status, message, recheck } = useAuth();

  if (status === 'checking') {
    return <div className="center-screen"><LoadingState label="Connecting to the API…" /></div>;
  }
  if (status === 'error') {
    return (
      <div className="center-screen">
        <ErrorState title="Cannot reach the API" error={{ message }} onRetry={recheck} />
      </div>
    );
  }
  if (status !== 'authenticated') return <Login />;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="farms" element={<Farms />} />
        <Route path="lots" element={<Lots />} />
        <Route path="varieties" element={<Varieties />} />
        <Route path="crops" element={<Crops />} />
        <Route path="seasons" element={<Seasons />} />
        <Route path="harvests" element={<Harvests />} />
        <Route path="forecasts" element={<Forecasts />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

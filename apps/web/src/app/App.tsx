import { Route, Routes } from "react-router-dom";
import AppLayout from "../components/layout/AppLayout";
import FocusLayout from "../components/layout/FocusLayout";
import DashboardPage from "../pages/dashboard/DashboardPage";
import ProgressPage from "../pages/progress/ProgressPage";
import SettingsPage from "../pages/settings/SettingsPage";
import PreparationHubPage from "../pages/preparation/PreparationHubPage";
import NewPreparationPage from "../pages/new-preparation/NewPreparationPage";
import InterviewRoomPage from "../pages/interview/InterviewRoomPage";
import GradingPage from "../pages/grading/GradingPage";
import ReportPage from "../pages/report/ReportPage";
import VoiceCheckPage from "../pages/voice-check/VoiceCheckPage";
import NotFoundPage from "../pages/not-found/NotFoundPage";
import "./App.css";

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="preparations/new" element={<NewPreparationPage />} />
        <Route path="preparations/:preparationId" element={<PreparationHubPage />} />
        <Route path="grading/:sessionId" element={<GradingPage />} />
        <Route path="reports/:reportId" element={<ReportPage />} />
        <Route path="progress" element={<ProgressPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
      <Route element={<FocusLayout />}>
        <Route path="interview/:sessionId" element={<InterviewRoomPage />} />
      </Route>
      <Route path="voice-check" element={<VoiceCheckPage />} />
    </Routes>
  );
}

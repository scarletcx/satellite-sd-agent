import { Layout, Menu, Tag } from "antd";
import { Link, Route, Routes, useLocation } from "react-router-dom";

import MissionCreate from "./pages/MissionCreate";
import MissionDetail from "./pages/MissionDetail";
import Knowledge from "./pages/Knowledge";
import Settings from "./pages/Settings";

const { Header, Content } = Layout;

export default function App() {
  const location = useLocation();
  const selected = location.pathname.startsWith("/kb") ? ["kb"]
    : location.pathname.startsWith("/settings") ? ["settings"] : ["missions"];

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header style={{ display: "flex", alignItems: "center", gap: 24 }}>
        <div style={{ color: "#fff", fontWeight: 600, whiteSpace: "nowrap" }}>AI 卫星总体设计助手</div>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={selected}
          style={{ flex: 1, minWidth: 0 }}
          items={[
            { key: "missions", label: <Link to="/">设计任务</Link> },
            { key: "kb", label: <Link to="/kb">知识库</Link> },
            { key: "settings", label: <Link to="/settings">设置</Link> },
          ]}
        />
        <Tag color="blue">v0.1</Tag>
      </Header>
      <Content style={{ padding: 24, width: "100%", maxWidth: 1200, margin: "0 auto" }}>
        <Routes>
          <Route path="/" element={<MissionCreate />} />
          <Route path="/missions/:taskId" element={<MissionDetail />} />
          <Route path="/kb" element={<Knowledge />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </Content>
    </Layout>
  );
}

import { Container, getContainer } from "@cloudflare/containers";

// Cloudflare Container가 Streamlit 서버를 8501 포트에서 실행합니다.
export class StreamlitContainer extends Container {
  defaultPort = 8501;
  sleepAfter = "10m";
}

export default {
  fetch(request, env) {
    // 모든 요청과 Streamlit WebSocket 세션을 같은 앱 인스턴스로 전달합니다.
    return getContainer(env.STREAMLIT_CONTAINER, "seoul-jeonse-dashboard").fetch(
      request,
    );
  },
};


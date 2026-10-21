{{flutter_js}}
{{flutter_build_config}}

// Only startup status crosses the frame boundary. Lessons and progress remain
// owned by the learner; the desktop shell checks the sending window's identity.
const embedded = window.parent !== window && new URLSearchParams(window.location.search).get('desktop') === '1';
function notifyDesktop(type) {
  if (embedded) window.parent.postMessage({ channel: 'neurolearn-desktop', type }, '*');
}
function fail() {
  notifyDesktop('error');
  const status = document.getElementById('startup-status');
  if (status) status.textContent = "Learn couldn't start. Reload to try again.";
}

_flutter.loader.load({
  onEntrypointLoaded: async function(engineInitializer) {
    try {
      const appRunner = await engineInitializer.initializeEngine();
      await appRunner.runApp();
      document.getElementById('startup-status')?.remove();
      notifyDesktop('ready');
    } catch (error) {
      console.error('NeuroLearn startup failed', error);
      fail();
    }
  }
}).catch(fail);

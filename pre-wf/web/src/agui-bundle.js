// src/agui-bundle.js
// Entry point for webpack bundle

// Import the AG-UI client components
import { 
  HttpAgent,
  runHttpRequest,
  parseSSEStream,
  transformHttpEventStream,
  EventType,
  AGUIError,
  RunAgentInputSchema
} from '@ag-ui/client';

// Export everything we want to make available globally
export {
  HttpAgent,
  runHttpRequest,
  parseSSEStream,
  transformHttpEventStream,
  EventType,
  AGUIError,
  RunAgentInputSchema
};

// Also make it available on window object for easier access
if (typeof window !== 'undefined') {
  window.AGUI = {
    HttpAgent,
    runHttpRequest,
    parseSSEStream,
    transformHttpEventStream,
    EventType,
    AGUIError,
    RunAgentInputSchema
  };
}
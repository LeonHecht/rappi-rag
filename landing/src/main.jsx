import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import Landing from './Landing';
import { APP_NAME } from './config/appConfig';

document.title = APP_NAME;

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Landing />
  </React.StrictMode>,
);

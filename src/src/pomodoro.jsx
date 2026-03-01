import './App.css';

import { useState, useEffect, useRef, useCallback } from "react";

const MODES = {
  work: { label: "FOCUS", duration: 1 * 3 }, // 3 seconds for testing
  short: { label: "SHORT BREAK", duration: 5 * 60 },
  long: { label: "LONG BREAK", duration: 15 * 60 },
};


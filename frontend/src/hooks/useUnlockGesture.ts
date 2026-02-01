"use client";

import { useState, useRef, useCallback, useEffect } from "react";

// Long press duration in milliseconds
export const UNLOCK_HOLD_DURATION_MS = 2000;

// Progress ring circumference constants (2 * PI * radius)
export const PROGRESS_RING_CIRCUMFERENCE_LARGE = 125.6; // radius = 20
export const PROGRESS_RING_CIRCUMFERENCE_SMALL = 75.4;  // radius = 12

interface UseUnlockGestureOptions {
  /** Whether the control is currently locked */
  isLocked: boolean;
  /** Callback when unlock gesture completes */
  onUnlock?: () => void;
  /** Duration in minutes before re-locking (0 = single action only) */
  unlockDurationMinutes?: number;
  /** Whether the lock period is currently active (from server) */
  lockActive?: boolean;
}

interface UseUnlockGestureReturn {
  /** Whether the control is currently unlocked (user has performed unlock gesture) */
  isUnlocked: boolean;
  /** Progress of the unlock gesture (0-1) */
  unlockProgress: number;
  /** Whether the user is currently holding to unlock */
  isHoldingToUnlock: boolean;
  /** Start the unlock hold gesture */
  startUnlockHold: () => void;
  /** Cancel the unlock hold gesture */
  cancelUnlockHold: () => void;
  /** Call after a control action to handle single-action unlock mode */
  handleControlAction: () => void;
  /** Manually set unlocked state (for child components triggering parent unlock) */
  setIsUnlocked: (value: boolean) => void;
  /** Ref to the expiry timer for external management */
  unlockExpiryTimerRef: React.MutableRefObject<NodeJS.Timeout | null>;
}

/**
 * Custom hook for managing the unlock gesture for sleep-locked controls.
 *
 * Provides long-press unlock functionality with visual progress feedback,
 * optional temporary unlock duration, and single-action unlock mode.
 */
export function useUnlockGesture({
  isLocked,
  onUnlock,
  unlockDurationMinutes = 5,
  lockActive = true,
}: UseUnlockGestureOptions): UseUnlockGestureReturn {
  const [isUnlocked, setIsUnlocked] = useState(false);
  const [unlockProgress, setUnlockProgress] = useState(0);
  const [isHoldingToUnlock, setIsHoldingToUnlock] = useState(false);

  const unlockTimerRef = useRef<NodeJS.Timeout | null>(null);
  const unlockStartTimeRef = useRef<number | null>(null);
  const unlockAnimationRef = useRef<number | null>(null);
  const unlockExpiryTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Clear unlock state when lock becomes inactive
  useEffect(() => {
    if (!lockActive) {
      setIsUnlocked(false);
      setUnlockProgress(0);
      // Clear expiry timer to prevent stale callbacks
      if (unlockExpiryTimerRef.current) {
        clearTimeout(unlockExpiryTimerRef.current);
        unlockExpiryTimerRef.current = null;
      }
    }
  }, [lockActive]);

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      if (unlockTimerRef.current) clearTimeout(unlockTimerRef.current);
      if (unlockAnimationRef.current) cancelAnimationFrame(unlockAnimationRef.current);
      if (unlockExpiryTimerRef.current) clearTimeout(unlockExpiryTimerRef.current);
    };
  }, []);

  const startUnlockHold = useCallback(() => {
    if (!isLocked) return;

    setIsHoldingToUnlock(true);
    unlockStartTimeRef.current = Date.now();

    // Animate progress
    const animateProgress = () => {
      if (!unlockStartTimeRef.current) return;

      const elapsed = Date.now() - unlockStartTimeRef.current;
      const progress = Math.min(1, elapsed / UNLOCK_HOLD_DURATION_MS);
      setUnlockProgress(progress);

      if (progress < 1) {
        unlockAnimationRef.current = requestAnimationFrame(animateProgress);
      }
    };
    unlockAnimationRef.current = requestAnimationFrame(animateProgress);

    // Set timer for unlock completion
    unlockTimerRef.current = setTimeout(() => {
      setIsUnlocked(true);
      setIsHoldingToUnlock(false);
      setUnlockProgress(0);
      onUnlock?.();

      // Set expiry timer for temporary unlock
      if (unlockDurationMinutes > 0) {
        unlockExpiryTimerRef.current = setTimeout(() => {
          setIsUnlocked(false);
        }, unlockDurationMinutes * 60 * 1000);
      }
    }, UNLOCK_HOLD_DURATION_MS);
  }, [isLocked, onUnlock, unlockDurationMinutes]);

  const cancelUnlockHold = useCallback(() => {
    setIsHoldingToUnlock(false);
    setUnlockProgress(0);
    unlockStartTimeRef.current = null;

    if (unlockTimerRef.current) {
      clearTimeout(unlockTimerRef.current);
      unlockTimerRef.current = null;
    }
    if (unlockAnimationRef.current) {
      cancelAnimationFrame(unlockAnimationRef.current);
      unlockAnimationRef.current = null;
    }
  }, []);

  // Handle single-action unlock mode (re-lock after one action)
  const handleControlAction = useCallback(() => {
    if (unlockDurationMinutes === 0 && isUnlocked) {
      // Re-lock immediately after single action
      setIsUnlocked(false);
    }
  }, [unlockDurationMinutes, isUnlocked]);

  return {
    isUnlocked,
    unlockProgress,
    isHoldingToUnlock,
    startUnlockHold,
    cancelUnlockHold,
    handleControlAction,
    setIsUnlocked,
    unlockExpiryTimerRef,
  };
}

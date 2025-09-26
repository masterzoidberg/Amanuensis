    def _concurrent_recording_loop(self):
        """Concurrent recording loop using python-soundcard for both mic and system audio"""
        self.logger.debug("Concurrent recording loop thread started")
        self._thread_running = True

        try:
            # Notify GUI that thread is starting
            self.status_queue.put({
                'type': 'thread_status',
                'status': 'starting',
                'message': 'Concurrent recording initializing...'
            })

            # Check for shutdown before starting
            if self._shutdown_event.is_set():
                self.logger.info("Shutdown requested before recording start")
                return

            buffer_max_size = int(self.buffer_duration * self.sample_rate / self.chunk_size)
            self.logger.info(f"Concurrent recording loop ready - Buffer max size: {buffer_max_size} chunks ({self.buffer_duration}s)")

            chunk_count = 0
            last_level_log = 0

            # Notify GUI that recording is ready
            self.status_queue.put({
                'type': 'thread_status',
                'status': 'running',
                'message': 'Concurrent recording active'
            })

            self.logger.debug("Starting concurrent soundcard recording streams...")

            # Start concurrent recording using context managers
            with self.microphone_recorder as mic_rec, self.loopback_recorder as sys_rec:
                self.logger.info(f"Recording started - Mic: {self.microphone_device.name}, System: {self.system_audio_device.name}")

                while self.recording and not self._shutdown_event.is_set():
                    try:
                        # Check for commands from GUI
                        try:
                            command = self.command_queue.get_nowait()
                            if command['command'] == 'stop':
                                self.logger.debug("Stop command received from GUI")
                                break
                        except queue.Empty:
                            pass

                        # Record from both sources concurrently
                        mic_data = mic_rec.record(numframes=self.chunk_size)  # Shape: (chunk_size,) mono
                        sys_data = sys_rec.record(numframes=self.chunk_size)  # Shape: (chunk_size, 2) stereo

                        # Convert to consistent format
                        mic_audio = (mic_data * 32767).astype(np.int16)  # Convert float32 to int16
                        if sys_data.ndim == 2:
                            # Convert stereo to mono by averaging channels
                            sys_audio = ((np.mean(sys_data, axis=1)) * 32767).astype(np.int16)
                        else:
                            sys_audio = (sys_data * 32767).astype(np.int16)

                        # Calculate levels
                        mic_level = np.sqrt(np.mean(mic_audio.astype(float)**2))
                        sys_level = np.sqrt(np.mean(sys_audio.astype(float)**2))

                        # Update levels (thread-safe)
                        with self._levels_lock:
                            self._mic_level = mic_level
                            self._system_level = sys_level

                        # Combine channels: Left = Mic (THERAPIST), Right = System Audio (CLIENT)
                        stereo_data = np.empty(len(mic_audio) * 2, dtype=np.int16)
                        stereo_data[0::2] = mic_audio   # Left channel (even indices)
                        stereo_data[1::2] = sys_audio   # Right channel (odd indices)

                        # Send audio data to registered callbacks for real-time transcription
                        stereo_float = stereo_data.astype(np.float32) / 32768.0
                        self._call_audio_callbacks(stereo_float, self.sample_rate)

                        # Add to buffer
                        timestamp = time.time()
                        self.audio_buffer.append({
                            'timestamp': timestamp,
                            'mic_data': mic_audio,
                            'system_data': sys_audio,
                            'stereo_data': stereo_data,
                            'mic_level': mic_level,
                            'system_level': sys_level
                        })

                        # Trim buffer if it exceeds maximum size
                        while len(self.audio_buffer) > buffer_max_size:
                            self.audio_buffer.popleft()

                        chunk_count += 1

                        # Update buffer duration
                        if self.audio_buffer:
                            duration = (self.audio_buffer[-1]['timestamp'] -
                                      self.audio_buffer[0]['timestamp'])
                            self._buffer_duration = duration

                        # Periodic status log (every 5 seconds)
                        if time.time() - last_level_log > 5:
                            buffer_duration = len(self.audio_buffer) * self.chunk_size / self.sample_rate
                            self.logger.debug(f"Recording: {chunk_count} chunks, buffer: {buffer_duration:.1f}s, mic: {mic_level:.0f}, sys: {sys_level:.0f}")
                            last_level_log = time.time()

                    except Exception as e:
                        self.logger.error(f"Recording loop error: {e}")
                        # Try to continue recording unless it's a critical error
                        if "device" in str(e).lower() or "stream" in str(e).lower():
                            self.logger.error("Critical device error - stopping recording")
                            break
                        # For other errors, just log and continue
                        continue

            self.logger.info(f"Recording loop ended after {chunk_count} chunks")

        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Concurrent recording thread error: {e}")
            self.recording = False

            # Provide user-friendly error message
            if "device" in error_msg.lower():
                user_message = "Audio device error: The selected audio device may not be available or properly configured. Try selecting a different microphone or speaker device."
            else:
                user_message = f"Recording error: {error_msg}"

            try:
                self.status_queue.put({
                    'type': 'error',
                    'error': error_msg,
                    'user_message': user_message
                })
            except:
                pass  # Don't let queue errors prevent cleanup

        finally:
            self.logger.debug("Cleaning up concurrent recording streams...")
            self._thread_running = False

            # Soundcard recorders are context managers - they clean up automatically
            self.microphone_recorder = None
            self.loopback_recorder = None

            # Notify GUI that recording stopped
            try:
                self.status_queue.put({
                    'type': 'thread_status',
                    'status': 'stopped',
                    'message': 'Concurrent recording thread finished'
                })
            except:
                pass  # Don't let notification errors affect cleanup

            self.logger.debug("Concurrent recording loop thread finished")
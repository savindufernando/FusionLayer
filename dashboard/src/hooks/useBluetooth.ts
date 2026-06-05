import { useState, useCallback, useRef } from 'react';

const SERVICE_UUID = '4fafc201-1fb5-459e-8fcc-c5c9c331914b';
const CHARACTERISTIC_UUID = 'beb5483e-36e1-4688-b7f5-ea07361b26a8';

export function useBluetooth() {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const characteristicRef = useRef<any>(null);

  const connect = useCallback(async () => {
    try {
      setError(null);
      const nav = navigator as any;
      if (!nav.bluetooth) {
        throw new Error('Web Bluetooth API is not available in this browser. Please use Chrome or Edge.');
      }

      const device = await nav.bluetooth.requestDevice({
        filters: [{ name: 'DriveGuard_LED_Stick' }],
        optionalServices: [SERVICE_UUID]
      });

      device.addEventListener('gattserverdisconnected', () => {
        setIsConnected(false);
        characteristicRef.current = null;
      });

      if (!device.gatt) throw new Error('No GATT server found on device');
      
      const server = await device.gatt.connect();
      const service = await server.getPrimaryService(SERVICE_UUID);
      const characteristic = await service.getCharacteristic(CHARACTERISTIC_UUID);

      characteristicRef.current = characteristic;
      setIsConnected(true);
      
      // Send boot color
      sendCommand('GREEN');
      
    } catch (err: any) {
      console.error('Bluetooth connect error:', err);
      setError(err.message || 'Failed to connect to Bluetooth device');
    }
  }, []);

  const sendCommand = useCallback(async (command: 'GREEN' | 'YELLOW' | 'RED' | 'OFF') => {
    if (!isConnected || !characteristicRef.current) return;
    try {
      const encoder = new TextEncoder();
      const value = encoder.encode(command);
      await characteristicRef.current.writeValue(value);
    } catch (err) {
      console.error('Failed to send Bluetooth command:', err);
    }
  }, [isConnected]);

  return { isConnected, error, connect, sendCommand };
}

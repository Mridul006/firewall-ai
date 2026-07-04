import { useWebSocket } from '../hooks/useWebSocket'

export default function AlertBanner() {
  const { messages, connected, error, dismiss } = useWebSocket('/api/v1/ws/alerts')

  return (
    <div className="border-b border-gray-200 bg-gray-50 px-4 py-2 dark:border-gray-700 dark:bg-gray-900">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-500">
          Live alerts:{' '}
          <span className={connected ? 'text-green-600' : 'text-gray-400'}>
            {connected ? 'connected' : 'disconnected'}
          </span>
        </span>
        {error && <span className="text-xs text-red-500">{error}</span>}
      </div>

      {messages.length > 0 && (
        <ul className="mt-1 space-y-1">
          {messages.map((msg, index) => (
            <li
              key={index}
              className="flex items-center justify-between rounded-md bg-yellow-50 px-3 py-1.5 text-sm text-yellow-800"
            >
              <span>{msg.message || JSON.stringify(msg)}</span>
              <button
                type="button"
                onClick={() => dismiss(index)}
                className="ml-2 text-yellow-600 hover:text-yellow-900"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

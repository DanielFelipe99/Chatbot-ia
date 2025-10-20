<?php
namespace OllamaIAService;
use ArdaGnsrn\Ollama\Ollama;

class OllamaIAService
{
    protected $client;

    public function __construct()
    {
        try {
            $ollamaUrl = $_ENV['OLLAMA_URL'] ?? 'http://localhost:11434';
            $this->client = Ollama::client($ollamaUrl);
            error_log('Ollama client creado exitosamente');
        } catch (\Exception $e) {
            error_log('Error creando Ollama client: ' . $e->getMessage());
            throw $e;
        }
    }

    public function getResponseWithModel(
        string $prompt,
        string $model = 'phi3:mini',
        float $temperature = 0.3,
        int $maxTokens = 160
    ): string {
        try {
            $startTime = microtime(true);
            $promptLength = strlen($prompt);
            $effectiveTokens = max(60, min($maxTokens, 160));

            if ($promptLength < 120) {
                $effectiveTokens = min($effectiveTokens, 80);
            }

            $adjustedTemperature = min($temperature, 0.45);

            error_log(
                "OllamaService: Modelo $model, tokens=$effectiveTokens, " .
                "temp=$adjustedTemperature, len=$promptLength"
            );

            $truncatedPrompt = substr($prompt, 0, 1600);

            $options = [
                'temperature' => $adjustedTemperature,
                'num_predict' => $effectiveTokens,
                'top_k' => 30,
                'top_p' => 0.9,
                'repeat_penalty' => 1.08,
                'stop' => ["\n\n", 'Pregunta:', 'Usuario:', 'PREGUNTA:'],
            ];

            $result = $this->client->completions()->create([
                'model' => $model,
                'prompt' => $truncatedPrompt,
                'stream' => false,
                'options' => $options,
            ]);

            $response = $result->response ?? 'Sin respuesta';
            $response = trim($response);

            $response = preg_replace('/^(Respuesta|RESPUESTA):\s*/i', '', $response);
            $response = preg_replace('/^Profesor Alex:\s*/i', '', $response);

            if (!preg_match('/[.!?]$/', $response)) {
                error_log('⚠️ Respuesta sin puntuación final');

                if (preg_match('/^(.+[.!?])\s*[^.!?]*$/', $response, $matches)) {
                    $response = $matches[1];
                    error_log('✂️ Cortado en última oración completa');
                } else {
                    $response .= '.';
                }
            }

            $sentences = preg_split('/(?<=[.!?])\s+/', $response);
            if (count($sentences) > 4) {
                $response = implode(' ', array_slice($sentences, 0, 4));
                error_log('✂️ Limitado a 4 oraciones');
            }

            $elapsed = round((microtime(true) - $startTime) * 1000);
            $charCount = strlen($response);
            $sentenceCount = count($sentences);

            error_log("⚡ Tiempo: {$elapsed}ms | Chars: {$charCount} | Oraciones: {$sentenceCount}");

            return $response;
        } catch (\Exception $e) {
            error_log('Error Ollama: ' . $e->getMessage());
            throw $e;
        }
    }

    public function getResponseWithParams($prompt, $model, $temp, $tokens): string
    {
        return $this->getResponseWithModel($prompt, $model, $temp, $tokens);
    }

    public function getQuickResponse(string $prompt, string $context): string
    {
        try {
            $model = $_ENV['FAST_MODEL'] ?? 'phi3:mini';

            $fullPrompt = "Contexto relevante:\n{$context}\n\n" .
                "Pregunta: {$prompt}\n" .
                "Respuesta breve y específica:";

            $result = $this->client->completions()->create([
                'model' => $model,
                'prompt' => $fullPrompt,
                'stream' => false,
                'options' => [
                    'num_predict' => 100,
                    'temperature' => 0.25,
                    'top_k' => 40,
                    'top_p' => 0.95,
                    'repeat_penalty' => 1.1,
                ],
            ]);

            return $result->response ?? 'Sin respuesta';
        } catch (\Exception $e) {
            error_log('Error: ' . $e->getMessage());
            return 'Error procesando la pregunta.';
        }
    }
}

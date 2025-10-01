<?php
namespace OllamaIAService;

use ArdaGnsrn\Ollama\Ollama;

class OllamaIAService {
    protected $client;
    
    public function __construct() {
        try {
            $ollamaUrl = $_ENV['OLLAMA_URL'] ?? 'http://localhost:11434';
            $this->client = Ollama::client($ollamaUrl);
            error_log("Ollama client creado exitosamente");
        } catch (\Exception $e) {
            error_log("Error creando Ollama client: " . $e->getMessage());
            throw $e;
        }
    }
    public function getResponseWithModel(
        string $prompt,
        string $model = 'llama3',
        float $temperature = 0.5,
        int $maxTokens = 150
    ): string {
        try {
            error_log("OllamaService: Usando modelo $model");
            
            // Limitar prompt para evitar timeouts
            $truncatedPrompt = substr($prompt, 0, 2000);
            
            $result = $this->client->completions()->create([
                'model' => $model,
                'prompt' => $truncatedPrompt,
                'stream' => false,
                'options' => [
                    'temperature' => $temperature,
                    'num_predict' => $maxTokens,
                    'top_k' => 40,
                    'top_p' => 0.9
                ]
            ]);
            
            return $result->response ?? 'Sin respuesta';
            
        } catch (\Exception $e) {
            error_log("Error Ollama: " . $e->getMessage());
            
            // Si falla con phi3, intentar con llama3
            if ($model !== 'llama3') {
                error_log("Reintentando con llama3...");
                return $this->getResponseWithModel($prompt, 'llama3', $temperature, $maxTokens);
            }
            
            throw $e;
        }
    }
    
    // Mantén los métodos anteriores por compatibilidad
    public function getResponseWithParams($prompt, $model, $temp, $tokens): string {
        return $this->getResponseWithModel($prompt, $model, $temp, $tokens);
    }

    public function getQuickResponse(string $prompt, string $context): string {
        try {
            // Usar phi3:mini (3.8B) o llama3.2:1b (mucho más rápido)
            $model = $_ENV['FAST_MODEL'] ?? 'phi3:mini';
            
            // Prompt optimizado
            $fullPrompt = "Contexto relevante:\n{$context}\n\n" .
                         "Pregunta: {$prompt}\n" .
                         "Respuesta breve y específica:";
            
            $result = $this->client->completions()->create([
                'model' => $model,
                'prompt' => $fullPrompt,
                'stream' => false,
                'options' => [
                    'num_predict' => 100,  // Respuestas cortas
                    'temperature' => 0.3,   // Más determinístico
                    'top_k' => 10,          // Limitar vocabulario
                    'repeat_penalty' => 1.1
                ]
            ]);
            
            return $result->response ?? 'Sin respuesta';
            
        } catch (\Exception $e) {
            error_log("Error: " . $e->getMessage());
            return "Error procesando la pregunta.";
        }
    }
}
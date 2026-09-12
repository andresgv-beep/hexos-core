// Laboratorio únicamente: sustituye el formateador al enlazar, no el motor instalado.
// Cada generación empieza con KV vacío y el prompt literal de la plantilla oficial.
#include "inference_session.hpp"
#include <atomic>
#include <chrono>
#include <cstdio>
#include <iostream>
#include <iterator>
#include <string>

namespace helios {
std::string format_gemma4_chat(const std::vector<ChatMessage>& messages,
                               const Gemma4ChatOptions&) {
    if (messages.size()!=1) throw std::runtime_error("probe expects one raw prompt");
    return messages[0].content;
}
}

int main(int argc, char** argv) {
    if (argc!=2) return 2;
    std::cout.rdbuf(std::cerr.rdbuf());
    helios::InferenceSession session;
    std::string error, code;
    helios::Model::Config cfg;
    cfg.hnf_path=argv[1]; cfg.max_seq_len=8192;
    if (!session.load(cfg,&error)) { std::cerr<<error; return 1; }
    std::printf("READY\n"); std::fflush(stdout);
    std::string header;
    while (std::getline(std::cin,header)) {
        const size_t n=std::stoul(header);
        if(n>1024*1024) return 3;
        std::string prompt(n,'\0'); std::cin.read(prompt.data(),n);
        if(static_cast<size_t>(std::cin.gcount())!=n) return 4;
        session.reset();
        std::atomic<bool> stop{false};
        std::string output;
        bool tool_stop=false;
        helios::InferenceSession::GenConfig gen;
        gen.temperature=0; gen.max_visible_tokens=1536; gen.max_thinking_tokens=0;
        helios::InferenceSession::TurnStats stats;
        helios::InferenceSession::FinishReason reason;
        auto t=std::chrono::steady_clock::now();
        const bool ok=session.run_turn({{"user",prompt}}, {},gen,
            [&](const std::string& s){output+=s;
                if(output.find("<|tool_response>")!=std::string::npos){tool_stop=true;stop=true;}},
            {},{},stop,&stats,&reason,&code,&error);
        auto ms=std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-t).count();
        if(!ok) output="ERROR: "+code+" "+error;
        std::printf("%zu %ld %u %d %s\n",output.size(),ms,stats.generated_tokens,
                    tool_stop?1:0,ok?helios::InferenceSession::finish_reason_name(reason):"error");
        std::fwrite(output.data(),1,output.size(),stdout);std::fflush(stdout);
    }
}

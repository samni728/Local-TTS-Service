import asyncio
import edge_tts

async def check_guangxi_voices():
    try:
        voices = await edge_tts.list_voices()
        guangxi_voices = [v for v in voices if 'guangxi' in v['ShortName'].lower()]
        print(f"找到 {len(guangxi_voices)} 个广西音色:")
        for voice in guangxi_voices:
            print(f"  - {voice['ShortName']}: {voice.get('FriendlyName', 'N/A')}")
        
        # 检查特定音色
        target_voice = "zh-CN-guangxi-YunqiNeural"
        target_found = any(v['ShortName'] == target_voice for v in voices)
        print(f"\n目标音色 {target_voice} 是否可用: {'是' if target_found else '否'}")
        
        if target_found:
            voice_info = next(v for v in voices if v['ShortName'] == target_voice)
            print(f"音色信息: {voice_info}")
        
    except Exception as e:
        print(f"检查音色时出错: {e}")

if __name__ == "__main__":
    asyncio.run(check_guangxi_voices())
